"""
app/services/documentos_service.py
Motor de disparo do Formulário de Documentos do Hóspede — genérico e
customizável (ao contrário do formulário do condomínio, que é fixo pra
pets/pessoas/placa). Cada imóvel com `documentos_ativo=True` define, em
`Imovel.documentos_campos`, quais documentos/dados quer pedir (RG/CPF,
placa do carro, foto do pet etc).

Regra de envio (sem scheduler real, mesmo modelo do resto do projeto —
ver hospede_notificacoes.py): dispara via hook
oportunista + endpoint de cron, e é idempotente (checa `tentativas_envio`
antes de reenviar):

  • N dias antes do check-in (Imovel.documentos_dias_antes, padrão 3) -> envio único
  • O link expira DIAS_EXPIRA_APOS_CHECKOUT dias depois do check-out da estadia
"""
from __future__ import annotations

from datetime import date, timedelta
import json
import uuid

from flask import current_app

from app.extensions import db
from app.models import Imovel, Estadia, User, FormularioDocumentos
from app.services.email_service import enviar_email_formulario_documentos
from app.services.push_service import enviar_push_notificacao
from app.utils import deletar_arquivo_documento

DIAS_ANTES_PADRAO = 3
DIAS_EXPIRA_APOS_CHECKOUT = 3
MAX_TENTATIVAS = 1  # envio único (sem lembretes, diferente do condomínio)

# LGPD — minimização de dados: não faz sentido guardar documento pessoal
# do hóspede (RG/CPF, foto do pet etc.) indefinidamente depois que a
# estadia já terminou. 14 dias dá margem pro anfitrião resolver qualquer
# pendência (cobrança de dano, disputa etc.) sem manter o dado pra sempre.
DIAS_RETENCAO_DOCUMENTOS_APOS_CHECKOUT = 14

DEFAULT_CAMPOS_DOCUMENTOS = [
    {"nome": "RG ou CPF", "tipo": "foto", "obrigatorio": True},
    {"nome": "Placa do carro", "tipo": "texto", "obrigatorio": False},
    {"nome": "Foto do pet", "tipo": "foto", "obrigatorio": False},
]


def campos_do_imovel(imovel: Imovel) -> list:
    """Retorna a lista de campos configurada no imóvel, ou o modelo padrão."""
    raw = imovel.documentos_campos if imovel else None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                campos = []
                for c in parsed:
                    if not isinstance(c, dict) or not c.get("nome"):
                        continue
                    tipo = c.get("tipo") if c.get("tipo") in ("foto", "texto") else "texto"
                    campos.append({
                        "nome": c["nome"],
                        "tipo": tipo,
                        "obrigatorio": bool(c.get("obrigatorio")),
                    })
                if campos:
                    return campos
        except (json.JSONDecodeError, TypeError):
            pass
    return [dict(c) for c in DEFAULT_CAMPOS_DOCUMENTOS]


def _link_formulario(base_url: str, token: str) -> str:
    return f"{base_url}/documentos/{token}"


def processar_formularios_documentos(user: User, base_url: str) -> dict:
    """
    Varre as Estadias de imóveis com o formulário de documentos ativo e
    dispara o convite `documentos_dias_antes` dias antes do check-in.
    `base_url` sem barra final.
    """
    hoje = date.today()
    resultado = {"convites_enviados": 0}

    imoveis = Imovel.query.filter_by(user_id=user.id, documentos_ativo=True).all()
    if not imoveis:
        return resultado

    imoveis_map = {im.id: im for im in imoveis}
    houve_mudanca = False

    candidatos = Estadia.query.filter(
        Estadia.user_id == user.id,
        Estadia.imovel_id.in_(imoveis_map.keys()),
        Estadia.status.in_(["confirmada", "em_andamento"]),
        Estadia.email_hospede.isnot(None),
        Estadia.email_hospede != "",
        Estadia.data_checkin >= hoje - timedelta(days=1),  # tolerância p/ atraso
    ).all()

    for est in candidatos:
        im = imoveis_map.get(est.imovel_id)
        if not im:
            continue

        dias_antes = im.documentos_dias_antes if im.documentos_dias_antes is not None else DIAS_ANTES_PADRAO
        data_envio = est.data_checkin - timedelta(days=dias_antes)

        if hoje < data_envio:
            continue  # ainda não chegou a data desse envio

        form = est.formulario_documentos
        if form is None:
            expira_em = None
            if est.data_checkout:
                expira_em = est.data_checkout + timedelta(days=DIAS_EXPIRA_APOS_CHECKOUT)
            form = FormularioDocumentos(
                estadia_id=est.id,
                imovel_id=im.id,
                token=uuid.uuid4().hex,
                expira_em=expira_em,
                status="pendente",
                tentativas_envio=0,
            )
            db.session.add(form)

        if form.status == "respondido":
            continue

        if form.tentativas_envio >= MAX_TENTATIVAS:
            continue

        # Já enviado hoje? (evita reenvio duplicado dentro do mesmo dia)
        if form.data_ultimo_envio == hoje:
            continue

        link = _link_formulario(base_url, form.token)

        try:
            enviar_email_formulario_documentos(
                destinatario=est.email_hospede,
                nome_hospede=est.nome_hospede,
                imovel_titulo=im.titulo,
                link_formulario=link,
                data_checkin_fmt=est.data_checkin.strftime("%d/%m/%Y") if est.data_checkin else "",
            )
            form.tentativas_envio += 1
            form.data_ultimo_envio = hoje
            houve_mudanca = True
            resultado["convites_enviados"] += 1

            try:
                enviar_push_notificacao(
                    user,
                    titulo="Documentos solicitados ao hóspede",
                    corpo=f"Pedimos os documentos pra {est.nome_hospede} ({im.titulo})",
                    url="/imoveis",
                    tag="nomdo-documentos-hospede",
                )
            except Exception:
                current_app.logger.exception(
                    "Falha ao enviar push de formulário de documentos para a estadia %s", est.id
                )
        except Exception:
            current_app.logger.exception(
                "Falha ao enviar formulário de documentos para a estadia %s", est.id
            )

    if houve_mudanca:
        db.session.commit()

    return resultado


def apagar_documentos_antigos(user: User) -> dict:
    """
    LGPD — apaga os arquivos (RG/CPF, foto do pet etc.) e limpa as
    respostas dos formulários cuja estadia já fez check-out há mais de
    DIAS_RETENCAO_DOCUMENTOS_APOS_CHECKOUT dias. Idempotente: uma vez
    limpo, `respostas_json` fica vazio e o formulário não é mais
    candidato nas próximas execuções.
    """
    hoje = date.today()
    resultado = {"formularios_limpos": 0, "arquivos_apagados": 0}

    imoveis_ids = [
        im.id for im in Imovel.query.filter_by(user_id=user.id).all()
    ]
    if not imoveis_ids:
        return resultado

    limite = hoje - timedelta(days=DIAS_RETENCAO_DOCUMENTOS_APOS_CHECKOUT)

    candidatos = (
        FormularioDocumentos.query
        .join(Estadia, FormularioDocumentos.estadia_id == Estadia.id)
        .filter(
            FormularioDocumentos.imovel_id.in_(imoveis_ids),
            FormularioDocumentos.respostas_json.isnot(None),
            FormularioDocumentos.respostas_json != "[]",
            Estadia.data_checkout.isnot(None),
            Estadia.data_checkout <= limite,
        )
        .all()
    )

    houve_mudanca = False
    for form in candidatos:
        for resposta in (form.respostas or []):
            if resposta.get("tipo") == "foto" and resposta.get("valor"):
                deletar_arquivo_documento(resposta["valor"])
                resultado["arquivos_apagados"] += 1

        # Limpa também os campos de texto (placa do carro etc.) — mesma
        # lógica de minimização, não só as fotos.
        form.respostas = []
        resultado["formularios_limpos"] += 1
        houve_mudanca = True

    if houve_mudanca:
        db.session.commit()

    return resultado
