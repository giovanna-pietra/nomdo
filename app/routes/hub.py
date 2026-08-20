"""
app/routes/hub.py
API do Hub do Anfitrião — gerenciador operacional multi-imóvel.

Rotas:
  GET    /api/hub/dados                    → KPIs, imóveis com score, tarefas, lembretes
  POST   /api/hub/manutencao                → registra uma manutenção pontual em um imóvel
  POST   /api/hub/troca-pilha/<imovel_id>   → marca a pilha da fechadura como trocada hoje
  POST   /api/hub/tarefa/concluir/<id>      → alterna o status concluída/pendente de uma tarefa
  DELETE /api/hub/tarefa/excluir/<id>       → remove uma tarefa do checklist
  DELETE /api/hub/tarefa/limpar-historico   → remove em lote as tarefas de Cuidados do Imóvel já concluídas
  POST   /api/hub/checklist-modelo/<imovel_id> → salva o template de checklist de hospedagem do imóvel
  GET    /api/hub/lembretes                 → lista as rotinas/lembretes recorrentes cadastrados
  POST   /api/hub/lembretes/salvar          → cria ou edita uma rotina/lembrete
  POST   /api/hub/lembretes/toggle/<id>     → ativa/pausa uma rotina
  DELETE /api/hub/lembretes/excluir/<id>    → remove uma rotina
  DELETE /api/hub/lembretes/excluir-todas   → remove em lote todas as rotinas/lembretes
  GET    /api/hub/eventos                   → lista os eventos de precificação cadastrados
  POST   /api/hub/eventos/salvar            → cria ou edita um evento de precificação
  DELETE /api/hub/eventos/excluir/<id>      → remove um evento de precificação

Motor de disparo automático (processar_lembretes): roda a cada carregamento
do Hub (chamado tanto pela rota de página em main.py quanto por /api/hub/dados)
e é idempotente — usa o estado já salvo no banco (ultimo_envio, tarefas já
abertas, email_enviado) para nunca recriar uma tarefa/duplicar um e-mail à toa,
mesmo sendo chamado várias vezes ou por workers diferentes do gunicorn.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, request, session, url_for

from app.extensions import db
from app.models import Imovel, Estadia, HubTarefa, LembreteConfig, User, EventoPrecificacao
from app.models.hub import TIPOS_LEMBRETE, TIPOS_EVENTO
from app.models.precificacao import NIVEIS_IMPACTO
from app.services import eventos_service
from app.services.email_service import enviar_email_lembrete
from app.services.push_service import enviar_push_notificacao
from app.services.precificacao import calcular_oportunidades, _percentuais_do_usuario
from app.utils import login_required, get_effective_owner_id, url_arquivo_publico

hub_bp = Blueprint("hub", __name__)

DIAS_PILHA_PADRAO = 20
JANELA_LIMPEZA_RETROATIVA = 5  # dias — evita reprocessar checkouts muito antigos
JANELA_CHECKLIST_ANTES = 1     # dias de antecedência pra avisar do checklist antes do check-in


# ─────────────────────────────────────────────────────────────────────────────
# CHECKLIST DE HOSPEDAGEM (antes do check-in / depois do check-out)
# ─────────────────────────────────────────────────────────────────────────────

# Lista padrão usada quando o imóvel não tem um checklist customizado — o
# anfitrião edita isso direto no Hub do Anfitrião, no card "Checklist de
# Hospedagem" (Task #41: saiu do formulário de Imóveis).
DEFAULT_CHECKLIST_ITENS = [
    {"texto": "Limpar e higienizar todos os cômodos", "momento": "antes"},
    {"texto": "Repor toalhas e roupa de cama limpas", "momento": "antes"},
    {"texto": "Testar Wi-Fi e conexão", "momento": "antes"},
    {"texto": "Verificar chuveiro e água quente", "momento": "antes"},
    {"texto": "Repor itens de boas-vindas (café, água)", "momento": "antes"},
    {"texto": "Conferir fechadura/chave/senha de acesso", "momento": "antes"},
    {"texto": "Testar ar-condicionado/ventiladores", "momento": "antes"},
    {"texto": "Verificar danos ou itens faltando", "momento": "depois"},
    {"texto": "Recolher o lixo", "momento": "depois"},
    {"texto": "Lavar roupa de cama e toalhas usadas", "momento": "depois"},
    {"texto": "Repor produtos de limpeza gastos", "momento": "depois"},
    {"texto": "Conferir eletrodomésticos desligados", "momento": "depois"},
    {"texto": "Vistoriar geladeira (produtos vencidos)", "momento": "depois"},
]


def _checklist_template(imovel: Imovel) -> list[dict]:
    """
    Lê o template de checklist customizado do imóvel (editável aqui no
    próprio Hub, no card "Checklist de Hospedagem") ou cai na lista padrão
    DEFAULT_CHECKLIST_ITENS se ele nunca mexeu nisso.
    """
    raw = imovel.checklist_itens if imovel else None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return [
                    i for i in parsed
                    if isinstance(i, dict) and i.get("texto") and i.get("momento") in ("antes", "depois")
                ]
        except (json.JSONDecodeError, TypeError):
            pass
    return DEFAULT_CHECKLIST_ITENS


def _checklist_status(estadia: Estadia) -> dict:
    """Lê o dicionário {item_key: concluido} já marcado nesta estadia."""
    if not estadia or not estadia.checklist_status:
        return {}
    try:
        parsed = json.loads(estadia.checklist_status)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _item_key(momento: str, texto: str) -> str:
    return f"{momento}:{texto}"


def _checklist_para_estadia(estadia: Estadia, imovel: Imovel | None, momento_filtro: str) -> dict:
    """Monta a lista de itens (só de um momento) + progresso pra uma estadia."""
    template = [i for i in _checklist_template(imovel) if i["momento"] == momento_filtro]
    status = _checklist_status(estadia)
    itens = [
        {
            "key": _item_key(i["momento"], i["texto"]),
            "texto": i["texto"],
            "concluido": bool(status.get(_item_key(i["momento"], i["texto"]))),
        }
        for i in template
    ]
    return {
        "estadia_id": estadia.id,
        "hospede": estadia.nome_hospede,
        "imovel": imovel.titulo if imovel else "—",
        "itens": itens,
        "total": len(itens),
        "concluidos": sum(1 for i in itens if i["concluido"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR DE LEMBRETES
# ─────────────────────────────────────────────────────────────────────────────

def _criar_tarefa_e_notificar(
    user: User,
    imovel: Imovel | None,
    tipo: str,
    titulo: str,
    descricao: str | None = None,
    estadia_id: int | None = None,
    lembrete_config_id: int | None = None,
) -> HubTarefa:
    tarefa = HubTarefa(
        user_id=user.id,
        imovel_id=imovel.id if imovel else None,
        titulo=titulo,
        descricao=descricao,
        tipo=tipo,
        estadia_id=estadia_id,
        lembrete_config_id=lembrete_config_id,
    )
    db.session.add(tarefa)

    if user.notify_email and user.email:
        try:
            enviar_email_lembrete(
                destinatario=user.email,
                nome_usuario=user.nome,
                tipo=tipo,
                imovel_titulo=imovel.titulo if imovel else "Seus imóveis",
                titulo_tarefa=titulo,
                descricao=descricao,
                imovel_endereco=imovel.endereco if imovel else None,
            )
            tarefa.email_enviado = True
        except Exception:
            current_app.logger.exception("Falha ao enviar e-mail de lembrete do Hub")

    if user.notify_browser:
        try:
            meta = TIPOS_LEMBRETE.get(tipo, {"icone": "📌", "label": "Lembrete"})
            # `titulo` já vem com o nome do imóvel embutido (todo call-site
            # monta assim, ex: "Trocar pilha da fechadura — {im.titulo}") —
            # não repete de novo aqui, senão duplica no corpo da notificação.
            enviar_push_notificacao(
                user,
                titulo=f"{meta['icone']} {meta['label']}",
                corpo=titulo,
                url="/hub-anfitriao?tab=tarefas",
                tag=f"nomdo-lembrete-{tipo}",
            )
        except Exception:
            current_app.logger.exception("Falha ao enviar push de lembrete do Hub")

    return tarefa


def processar_lembretes(user: User) -> dict:
    """
    Avalia todas as rotinas do anfitrião (fixas + customizadas) e dispara
    tarefa + e-mail para as que estão vencidas. Seguro para ser chamado
    repetidamente — cada disparo só acontece uma vez por ciclo.
    """
    hoje = date.today()
    tarefas_criadas = 0

    imoveis = Imovel.query.filter_by(user_id=user.id).all()
    imoveis_por_id = {im.id: im for im in imoveis}

    todas_configs = LembreteConfig.query.filter_by(user_id=user.id).all()
    config_map = {(c.imovel_id, c.tipo): c for c in todas_configs}

    # ── 1) Pilha de fechadura digital ──────────────────────────
    # Regra padrão de 20 dias direto no campo Imovel.ultima_troca_pilha;
    # o anfitrião pode sobrescrever o intervalo (ou pausar) via LembreteConfig.
    for im in imoveis:
        cfg = config_map.get((im.id, "pilha_fechadura"))
        if cfg and not cfg.ativo:
            continue

        # Imóvel que nunca teve "última troca de pilha" preenchida não tem
        # rotina de pilha configurada ainda — antes isso caía no fallback de
        # dias_desde_troca_pilha() (retorna 999), o que fazia TODO imóvel
        # novo nascer com uma tarefa "vencida há 999 dias" sem o anfitrião
        # ter configurado nada. Só passa a cobrar depois que a data for
        # preenchida pelo menos uma vez.
        if im.ultima_troca_pilha is None:
            continue

        intervalo = cfg.intervalo_dias if (cfg and cfg.intervalo_dias) else DIAS_PILHA_PADRAO
        dias = im.dias_desde_troca_pilha()

        if dias >= intervalo:
            existe_pendente = HubTarefa.query.filter_by(
                user_id=user.id, imovel_id=im.id, tipo="pilha_fechadura", concluida=False
            ).first()
            if not existe_pendente:
                dias_txt = "nunca registrada" if dias >= 999 else f"{dias} dias sem troca"
                _criar_tarefa_e_notificar(
                    user, im, "pilha_fechadura",
                    f"Trocar pilha da fechadura — {im.titulo}",
                    descricao=f"Última troca: {dias_txt}. Recomendado a cada {intervalo} dias.",
                )
                tarefas_criadas += 1
            if cfg:
                cfg.ultimo_envio = hoje

    # ── 2) Limpeza pós-checkout ─────────────────────────────────
    limite = hoje - timedelta(days=JANELA_LIMPEZA_RETROATIVA)
    estadias_encerradas = (
        Estadia.query
        .filter(
            Estadia.user_id == user.id,
            Estadia.status.notin_(["cancelada", "bloqueio"]),
            Estadia.data_checkout <= hoje,
            Estadia.data_checkout >= limite,
        )
        .all()
    )
    for est in estadias_encerradas:
        cfg = config_map.get((est.imovel_id, "limpeza_checkout"))
        if cfg and not cfg.ativo:
            continue

        ja_existe = HubTarefa.query.filter_by(estadia_id=est.id, tipo="limpeza_checkout").first()
        if ja_existe:
            continue

        im = imoveis_por_id.get(est.imovel_id)
        _criar_tarefa_e_notificar(
            user, im,
            "limpeza_checkout",
            f"Limpar {im.titulo if im else 'imóvel'} após saída de {est.nome_hospede}",
            descricao=f"Checkout em {est.data_checkout.strftime('%d/%m/%Y')}.",
            estadia_id=est.id,
            lembrete_config_id=cfg.id if cfg else None,
        )
        tarefas_criadas += 1
        if cfg:
            cfg.ultimo_envio = hoje

    # ── 3) Rotinas customizadas por intervalo (eletrônicos, café, ──
    #      papel higiênico, outro) ────────────────────────────────
    for cfg in todas_configs:
        if not cfg.ativo or cfg.tipo in ("pilha_fechadura",) or cfg.tipo in TIPOS_EVENTO:
            continue

        dias_para = cfg.dias_para_vencer()
        if dias_para is None or dias_para > 0:
            continue

        existe_pendente = HubTarefa.query.filter_by(
            user_id=user.id, lembrete_config_id=cfg.id, concluida=False
        ).first()
        if not existe_pendente:
            im = imoveis_por_id.get(cfg.imovel_id)
            _criar_tarefa_e_notificar(
                user, im, cfg.tipo, cfg.label(),
                descricao=cfg.descricao,
                lembrete_config_id=cfg.id,
            )
            tarefas_criadas += 1
        cfg.ultimo_envio = hoje

    # ── 4) Checklist de hospedagem pendente (antes do check-in / depois ──
    #      do check-out) — mesma lógica de evento da limpeza pós-checkout,
    #      só que avisando quando o checklist ainda não foi todo marcado
    #      perto do check-in/check-out. É isso que faz o checklist salvo
    #      no editor de modelo de fato "aparecer em algum lugar": vira uma
    #      tarefa em Prioridades do Dia + um e-mail, igual às outras rotinas.
    estadias_proximas = (
        Estadia.query
        .filter(
            Estadia.user_id == user.id,
            Estadia.status.notin_(["cancelada", "bloqueio"]),
            Estadia.data_checkin >= hoje,
            Estadia.data_checkin <= hoje + timedelta(days=JANELA_CHECKLIST_ANTES),
        )
        .all()
    )
    for est in estadias_proximas:
        cfg = config_map.get((est.imovel_id, "checklist_antes"))
        if cfg and not cfg.ativo:
            continue
        if HubTarefa.query.filter_by(estadia_id=est.id, tipo="checklist_antes").first():
            continue

        im = imoveis_por_id.get(est.imovel_id)
        progresso = _checklist_para_estadia(est, im, "antes")
        if progresso["total"] == 0 or progresso["concluidos"] >= progresso["total"]:
            continue  # sem itens de "antes" cadastrados, ou já está tudo pronto

        faltam = progresso["total"] - progresso["concluidos"]
        _criar_tarefa_e_notificar(
            user, im,
            "checklist_antes",
            f"Checklist de entrada pendente — {im.titulo if im else 'imóvel'}",
            descricao=(
                f"Faltam {faltam} de {progresso['total']} itens antes do check-in de "
                f"{est.nome_hospede} em {est.data_checkin.strftime('%d/%m/%Y')}."
            ),
            estadia_id=est.id,
            lembrete_config_id=cfg.id if cfg else None,
        )
        tarefas_criadas += 1
        if cfg:
            cfg.ultimo_envio = hoje

    for est in estadias_encerradas:  # mesma janela retroativa já usada na limpeza pós-checkout
        cfg = config_map.get((est.imovel_id, "checklist_depois"))
        if cfg and not cfg.ativo:
            continue
        if HubTarefa.query.filter_by(estadia_id=est.id, tipo="checklist_depois").first():
            continue

        im = imoveis_por_id.get(est.imovel_id)
        progresso = _checklist_para_estadia(est, im, "depois")
        if progresso["total"] == 0 or progresso["concluidos"] >= progresso["total"]:
            continue  # sem itens de "depois" cadastrados, ou já está tudo pronto

        faltam = progresso["total"] - progresso["concluidos"]
        _criar_tarefa_e_notificar(
            user, im,
            "checklist_depois",
            f"Checklist de saída pendente — {im.titulo if im else 'imóvel'}",
            descricao=(
                f"Faltam {faltam} de {progresso['total']} itens depois do check-out de "
                f"{est.nome_hospede} em {est.data_checkout.strftime('%d/%m/%Y')}."
            ),
            estadia_id=est.id,
            lembrete_config_id=cfg.id if cfg else None,
        )
        tarefas_criadas += 1
        if cfg:
            cfg.ultimo_envio = hoje

    if tarefas_criadas or todas_configs:
        db.session.commit()

    return {"tarefas_criadas": tarefas_criadas}


def processar_push_checkin_hoje(user: User) -> dict:
    """
    Avisa o anfitrião, por push, de cada estadia com check-in previsto pra
    hoje — só push (não tem e-mail equivalente hoje). Idempotente via
    `Estadia.push_checkin_enviado`, mesmo padrão de `email_guia_enviado`.
    """
    hoje = date.today()
    resultado = {"avisos_enviados": 0}

    if not user.notify_browser:
        return resultado

    imoveis_por_id = {im.id: im for im in Imovel.query.filter_by(user_id=user.id).all()}
    if not imoveis_por_id:
        return resultado

    estadias_hoje = Estadia.query.filter(
        Estadia.user_id == user.id,
        Estadia.status.notin_(["cancelada", "bloqueio"]),
        Estadia.data_checkin == hoje,
        Estadia.push_checkin_enviado.is_(False),
    ).all()

    houve_mudanca = False
    for est in estadias_hoje:
        im = imoveis_por_id.get(est.imovel_id)
        try:
            enviar_push_notificacao(
                user,
                titulo="Check-in hoje",
                corpo=f"{est.nome_hospede} chega hoje em {im.titulo if im else 'um dos seus imóveis'}",
                url="/imoveis",
                tag=f"nomdo-checkin-{est.id}",
            )
            est.push_checkin_enviado = True
            resultado["avisos_enviados"] += 1
            houve_mudanca = True
        except Exception:
            current_app.logger.exception(
                "Falha ao enviar push de check-in do dia para a estadia %s", est.id
            )

    if houve_mudanca:
        db.session.commit()

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/hub/dados
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/dados")
@login_required
def hub_dados():
    # Os imóveis pertencem à conta Proprietária — se quem está logado é um
    # Anfitrião-ajudante, os dados/lembretes/preferências usados aqui são os
    # do Proprietário (user_id -> owner_id), não os da conta do ajudante.
    user_id = get_effective_owner_id()
    user = db.session.get(User, user_id)

    processar_lembretes(user)

    imoveis = Imovel.query.filter_by(user_id=user_id).all()

    hoje = date.today()

    proxima_estadia = (
        Estadia.query
        .filter(
            Estadia.user_id == user_id,
            Estadia.status.in_(["confirmada", "em_andamento"]),
            Estadia.data_checkin >= hoje,
        )
        .order_by(Estadia.data_checkin.asc())
        .first()
    )

    proximo_checkin = None
    checklist_antes = None
    if proxima_estadia:
        imovel_da_estadia = next((im for im in imoveis if im.id == proxima_estadia.imovel_id), None)
        if proxima_estadia.data_checkin == hoje:
            quando = "Hoje"
        elif proxima_estadia.data_checkin == hoje + timedelta(days=1):
            quando = "Amanhã"
        else:
            quando = proxima_estadia.data_checkin.strftime("%d/%m")
        proximo_checkin = {
            "quando": quando,
            "hora": proxima_estadia.hora_checkin,
            "hospede": proxima_estadia.nome_hospede,
            "imovel": imovel_da_estadia.titulo if imovel_da_estadia else "—",
        }
        checklist_antes = _checklist_para_estadia(proxima_estadia, imovel_da_estadia, "antes")

    # Checklist "depois" — última estadia que fez checkout recentemente
    # (mesma janela usada pra disparar o lembrete de limpeza pós-checkout).
    limite_checklist = hoje - timedelta(days=JANELA_LIMPEZA_RETROATIVA)
    ultima_saida = (
        Estadia.query
        .filter(
            Estadia.user_id == user_id,
            Estadia.status.notin_(["cancelada", "bloqueio"]),
            Estadia.data_checkout <= hoje,
            Estadia.data_checkout >= limite_checklist,
        )
        .order_by(Estadia.data_checkout.desc())
        .first()
    )
    checklist_depois = None
    if ultima_saida:
        imovel_da_saida = next((im for im in imoveis if im.id == ultima_saida.imovel_id), None)
        checklist_depois = _checklist_para_estadia(ultima_saida, imovel_da_saida, "depois")

    tarefas_abertas = (
        HubTarefa.query
        .filter_by(user_id=user_id, concluida=False)
        .order_by(HubTarefa.created_at.desc())
        .limit(100)
        .all()
    )

    lembretes = (
        LembreteConfig.query
        .filter_by(user_id=user_id)
        .order_by(LembreteConfig.created_at.desc())
        .all()
    )

    # ── Score operacional por imóvel ────────────────────────────
    dados_imoveis = []
    pilhas_vencidas = 0

    manutencoes_abertas = sum(1 for t in tarefas_abertas if t.tipo == "manutencao")
    limpezas_pendentes = sum(1 for t in tarefas_abertas if t.tipo == "limpeza_checkout")
    lembretes_vencidos = sum(
        1 for t in tarefas_abertas if t.tipo not in ("manutencao", "limpeza_checkout", "pilha_fechadura")
    )

    tarefas_abertas_por_imovel: dict[int, list[HubTarefa]] = {}
    for t in tarefas_abertas:
        if t.imovel_id:
            tarefas_abertas_por_imovel.setdefault(t.imovel_id, []).append(t)

    for im in imoveis:
        score = 100
        alertas = []

        # Só entra no score/alerta se o anfitrião já registrou alguma troca
        # de pilha pra esse imóvel — sem isso, dias_desde_troca_pilha() cai
        # no sentinela 999 (nunca registrada), e antes isso era tratado como
        # "vencidíssimo" e aparecia como alerta mesmo sem o anfitrião ter
        # configurado nada (mesmo bug já corrigido em processar_lembretes()).
        dias_pilha = im.dias_desde_troca_pilha()
        if im.ultima_troca_pilha is not None and dias_pilha >= DIAS_PILHA_PADRAO:
            score -= 25
            alertas.append("Pilha da fechadura vencida")
            pilhas_vencidas += 1

        tarefas_im = tarefas_abertas_por_imovel.get(im.id, [])
        mant_im = sum(1 for t in tarefas_im if t.tipo == "manutencao")
        limp_im = sum(1 for t in tarefas_im if t.tipo == "limpeza_checkout")
        outros_im = len(tarefas_im) - mant_im - limp_im

        score -= min(mant_im * 15, 30)
        score -= min(limp_im * 10, 20)
        score -= min(outros_im * 5, 15)

        if mant_im:
            alertas.append(f"{mant_im} manutenção(ões) em aberto")
        if limp_im:
            alertas.append(f"{limp_im} limpeza(s) pendente(s)")
        if outros_im:
            alertas.append(f"{outros_im} rotina(s) pendente(s)")

        score = max(score, 0)
        nivel = "excelente" if score >= 90 else ("atencao" if score >= 70 else "critico")

        dados_imoveis.append({
            "id": im.id,
            "titulo": im.titulo,
            "endereco": im.endereco,
            "score": score,
            "nivel": nivel,
            "alertas": alertas,
            "dias_pilha": dias_pilha if dias_pilha < 999 else None,
            "foto_principal": url_arquivo_publico(im.foto_principal),
        })

    dados_imoveis.sort(key=lambda x: x["score"])

    imoveis_titulo = {im.id: im.titulo for im in imoveis}

    tarefas_json = []
    for t in tarefas_abertas:
        meta = TIPOS_LEMBRETE.get(t.tipo, {"icone": "📌", "label": t.tipo})
        tarefas_json.append({
            "id": t.id,
            "titulo": t.titulo,
            "descricao": t.descricao,
            "tipo": t.tipo,
            "tipo_label": meta.get("label", t.tipo),
            "tipo_icone": meta.get("icone", "📌"),
            "tipo_cor": meta.get("cor", "#7c3aed"),
            "imovel_id": t.imovel_id,
            "imovel": imoveis_titulo.get(t.imovel_id, "—"),
            "estadia_id": t.estadia_id,
            "criado_em": t.created_at.strftime("%d/%m/%Y %H:%M"),
            "data_prevista": t.data_prevista.isoformat() if t.data_prevista else None,
            "data_prevista_fmt": t.data_prevista.strftime("%d/%m/%Y") if t.data_prevista else None,
        })

    lembretes_json = []
    for l in lembretes:
        dias_para = l.dias_para_vencer()
        meta = TIPOS_LEMBRETE.get(l.tipo, {"icone": "📌", "label": l.tipo})
        lembretes_json.append({
            "id": l.id,
            "tipo": l.tipo,
            "tipo_label": meta.get("label", l.tipo),
            "tipo_icone": meta.get("icone", "📌"),
            "titulo": l.label(),
            "descricao": l.descricao,
            "imovel_id": l.imovel_id,
            "imovel": imoveis_titulo.get(l.imovel_id, "—"),
            "intervalo_dias": l.intervalo_dias,
            "ativo": l.ativo,
            "por_evento": l.tipo in TIPOS_EVENTO,
            "ultimo_envio": l.ultimo_envio.strftime("%d/%m/%Y") if l.ultimo_envio else None,
            "dias_para_vencer": dias_para,
            "vencido": l.vencido(),
        })

    proximos_vencimentos = sorted(
        (l for l in lembretes_json if l["dias_para_vencer"] is not None and l["ativo"]),
        key=lambda x: x["dias_para_vencer"],
    )[:8]

    # ── Oportunidades de precificação (feriados + eventos) ──────
    # (remove a chave "data" — objeto date não é serializável em JSON;
    # o front usa "data_fmt", já formatada como string)
    dicas_precificacao = []
    for dica in calcular_oportunidades(user)[:30]:
        dica = dict(dica)
        dica.pop("data", None)
        dicas_precificacao.append(dica)

    return jsonify({
        "total_imoveis": len(imoveis),
        "manutencoes_abertas": manutencoes_abertas,
        "limpezas_pendentes": limpezas_pendentes,
        "pilhas_vencidas": pilhas_vencidas,
        "lembretes_vencidos": lembretes_vencidos,
        "tarefas_pendentes_total": len(tarefas_abertas),
        "proximo_checkin": proximo_checkin,
        "checklist_antes": checklist_antes,
        "checklist_depois": checklist_depois,
        "imoveis": dados_imoveis,
        "tarefas": tarefas_json,
        "lembretes": lembretes_json,
        "proximos_vencimentos": proximos_vencimentos,
        "tipos_disponiveis": TIPOS_LEMBRETE,
        "notify_email": bool(user.notify_email),
        "dicas_precificacao": dicas_precificacao,
        "niveis_impacto": NIVEIS_IMPACTO,
        "pct_precificacao": _percentuais_do_usuario(user),
    })


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/hub/manutencao
# ─────────────────────────────────────────────────────────────────────────────

def _parse_data_prevista(valor):
    """Converte "YYYY-MM-DD" (formato do <input type="date"> do front) numa
    date, ou None se vazio/ausente/inválido — data prevista é sempre
    opcional, então um valor malformado é tratado como "não informada" em
    vez de erro 400."""
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


@hub_bp.route("/api/hub/manutencao", methods=["POST"])
@login_required
def registrar_manutencao():
    user_id = get_effective_owner_id()
    data = request.get_json(silent=True) or {}

    imovel_id = data.get("imovel_id")
    titulo = (data.get("titulo") or "").strip()

    if not imovel_id or not titulo:
        return jsonify({"success": False, "message": "Imóvel e título são obrigatórios."}), 400

    imovel = Imovel.query.filter_by(id=imovel_id, user_id=user_id).first()
    if not imovel:
        return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    tarefa = HubTarefa(
        user_id=user_id,
        imovel_id=imovel_id,
        titulo=titulo,
        descricao=data.get("descricao", ""),
        tipo=data.get("tipo") or "manutencao",
        data_prevista=_parse_data_prevista(data.get("data_prevista")),
        concluida=False,
    )
    db.session.add(tarefa)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Registrado em {imovel.titulo}.",
        "tarefa_id": tarefa.id,
    })


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/hub/troca-pilha/<imovel_id>
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/troca-pilha/<int:imovel_id>", methods=["POST"])
@login_required
def registrar_troca_pilha(imovel_id: int):
    user_id = get_effective_owner_id()

    imovel = Imovel.query.filter_by(id=imovel_id, user_id=user_id).first()
    if not imovel:
        return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    imovel.ultima_troca_pilha = date.today()

    # Fecha qualquer tarefa pendente de troca de pilha para esse imóvel.
    pendentes = HubTarefa.query.filter_by(
        user_id=user_id, imovel_id=imovel_id, tipo="pilha_fechadura", concluida=False
    ).all()
    for t in pendentes:
        t.concluida = True

    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Pilha de {imovel.titulo} registrada como trocada hoje.",
        "nova_data": imovel.ultima_troca_pilha.strftime("%d/%m/%Y"),
    })


# ─────────────────────────────────────────────────────────────────────────────
# TAREFAS — concluir / excluir
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/tarefa/concluir/<int:tarefa_id>", methods=["POST"])
@login_required
def concluir_tarefa(tarefa_id: int):
    user_id = get_effective_owner_id()

    tarefa = HubTarefa.query.filter_by(id=tarefa_id, user_id=user_id).first()
    if not tarefa:
        return jsonify({"success": False, "message": "Tarefa não encontrada."}), 404

    tarefa.concluida = not tarefa.concluida

    # Se for a tarefa de troca de pilha, marcar como trocada de fato no imóvel.
    if tarefa.concluida and tarefa.tipo == "pilha_fechadura" and tarefa.imovel_id:
        imovel = db.session.get(Imovel, tarefa.imovel_id)
        if imovel:
            imovel.ultima_troca_pilha = date.today()

    db.session.commit()

    return jsonify({"success": True, "concluida": tarefa.concluida})


@hub_bp.route("/api/hub/tarefa/excluir/<int:tarefa_id>", methods=["DELETE"])
@login_required
def excluir_tarefa(tarefa_id: int):
    user_id = get_effective_owner_id()

    tarefa = HubTarefa.query.filter_by(id=tarefa_id, user_id=user_id).first()
    if not tarefa:
        return jsonify({"success": False, "message": "Tarefa não encontrada."}), 404

    db.session.delete(tarefa)
    db.session.commit()

    return jsonify({"success": True})


@hub_bp.route("/api/hub/tarefa/limpar-historico", methods=["DELETE"])
@login_required
def limpar_historico_tarefas():
    """Exclui em lote todas as tarefas de Cuidados do Imóvel já concluídas —
    botão "Limpar histórico" da aba. Respeita os mesmos filtros de
    imóvel/tipo aplicados na tela (querystring `imovel_id`/`tipo`, os mesmos
    usados por `contexto_tarefas()` em pg_tarefas.py), pra só apagar o que a
    pessoa está de fato vendo na lista.

    Só afeta os tipos operacionais (limpeza/manutenção/comprar/repor/
    personalizado) — nunca mexe em concluídos de outras naturezas (ex:
    checklist_antes/depois), que nem aparecem nesta aba.
    """
    from app.routes.pg_tarefas import TIPOS_OPERACIONAIS

    user_id = get_effective_owner_id()
    query = HubTarefa.query.filter_by(user_id=user_id, concluida=True).filter(
        HubTarefa.tipo.in_(TIPOS_OPERACIONAIS)
    )

    raw_imovel_id = request.args.get("imovel_id")
    if raw_imovel_id:
        query = query.filter(HubTarefa.imovel_id == int(raw_imovel_id))

    tipo = request.args.get("tipo")
    if tipo in TIPOS_OPERACIONAIS:
        query = query.filter(HubTarefa.tipo == tipo)

    quantidade = query.count()
    query.delete(synchronize_session=False)
    db.session.commit()

    return jsonify({"success": True, "quantidade": quantidade})


@hub_bp.route("/api/hub/tarefa/editar/<int:tarefa_id>", methods=["POST"])
@login_required
def editar_tarefa(tarefa_id: int):
    """Edita título/descrição de uma tarefa existente (limpeza ou manutenção).

    Usado pelas páginas dedicadas de Limpezas/Manutenções — o endpoint de
    criação (`/api/hub/manutencao`) não suporta edição, só criação, então
    isso preenche essa lacuna sem tocar no fluxo de criação existente.
    """
    user_id = get_effective_owner_id()

    tarefa = HubTarefa.query.filter_by(id=tarefa_id, user_id=user_id).first()
    if not tarefa:
        return jsonify({"success": False, "message": "Tarefa não encontrada."}), 404

    dados = request.get_json(silent=True) or {}
    titulo = (dados.get("titulo") or "").strip()
    if not titulo:
        return jsonify({"success": False, "message": "Título é obrigatório."}), 400

    tarefa.titulo = titulo
    tarefa.descricao = (dados.get("descricao") or "").strip() or None
    if "data_prevista" in dados:
        tarefa.data_prevista = _parse_data_prevista(dados.get("data_prevista"))

    db.session.commit()

    return jsonify({
        "success": True,
        "tarefa": {
            "id": tarefa.id,
            "titulo": tarefa.titulo,
            "descricao": tarefa.descricao,
            "data_prevista": tarefa.data_prevista.isoformat() if tarefa.data_prevista else None,
        },
    })


@hub_bp.route("/api/hub/tarefas", methods=["GET"])
@login_required
def listar_tarefas_historico():
    """Histórico completo de tarefas (pendentes + concluídas), com filtros.

    Diferente de `/api/hub/dados`, que só devolve as pendentes (limitado a
    100) pra montar o resumo do Hub — este endpoint alimenta as páginas
    dedicadas de Limpezas/Manutenções/Rotinas, que precisam mostrar o
    histórico completo.

    Query params opcionais:
      - tipo: filtra por HubTarefa.tipo (ex: "manutencao", "limpeza_checkout")
      - concluida: "1"/"0" — filtra por status; omitido = todas
      - imovel_id: filtra por imóvel
      - limite: máximo de linhas (default 200)
    """
    user_id = get_effective_owner_id()

    query = HubTarefa.query.filter_by(user_id=user_id)

    tipo = request.args.get("tipo")
    if tipo:
        query = query.filter(HubTarefa.tipo == tipo)

    concluida = request.args.get("concluida")
    if concluida is not None and concluida != "":
        query = query.filter(HubTarefa.concluida == (concluida == "1"))

    imovel_id = request.args.get("imovel_id", type=int)
    if imovel_id:
        query = query.filter(HubTarefa.imovel_id == imovel_id)

    limite = request.args.get("limite", default=200, type=int)
    tarefas = query.order_by(HubTarefa.created_at.desc()).limit(limite).all()

    resultado = [{
        "id": t.id,
        "titulo": t.titulo,
        "descricao": t.descricao,
        "tipo": t.tipo,
        "imovel_id": t.imovel_id,
        "imovel": t.imovel.titulo if t.imovel_id and t.imovel else "—",
        "estadia_id": t.estadia_id,
        "concluida": t.concluida,
        "criado_em": t.created_at.strftime("%d/%m/%Y %H:%M") if t.created_at else None,
        "atualizado_em": t.updated_at.strftime("%d/%m/%Y %H:%M") if t.updated_at else None,
    } for t in tarefas]

    return jsonify({"success": True, "tarefas": resultado})


# ─────────────────────────────────────────────────────────────────────────────
# CHECKLIST DE HOSPEDAGEM — marcar/desmarcar item
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/checklist/toggle", methods=["POST"])
@login_required
def toggle_checklist_item():
    user_id = get_effective_owner_id()
    data = request.get_json(silent=True) or {}

    estadia_id = data.get("estadia_id")
    item_key = (data.get("item_key") or "").strip()

    if not estadia_id or not item_key:
        return jsonify({"success": False, "message": "Item inválido."}), 400

    estadia = Estadia.query.filter_by(id=estadia_id, user_id=user_id).first()
    if not estadia:
        return jsonify({"success": False, "message": "Estadia não encontrada."}), 404

    status = _checklist_status(estadia)
    novo_valor = not bool(status.get(item_key))
    status[item_key] = novo_valor
    estadia.checklist_status = json.dumps(status, ensure_ascii=False)
    db.session.commit()

    return jsonify({"success": True, "concluido": novo_valor})


@hub_bp.route("/api/hub/checklist-modelo/<int:imovel_id>", methods=["POST"])
@login_required
def salvar_checklist_modelo(imovel_id: int):
    """
    Salva o template de checklist de hospedagem (antes/depois) de um imóvel —
    migrou do formulário de Imóveis pra cá (Task #41), já que é aqui no Hub
    que o checklist é efetivamente usado a cada estadia.
    """
    try:
        owner_id = get_effective_owner_id()

        imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first()
        if not imovel:
            return jsonify({
                "success": False,
                "message": "Imóvel não encontrado."
            }), 404

        data = request.get_json(silent=True) or {}
        itens_brutos = data.get("itens") or []

        itens = []
        if isinstance(itens_brutos, list):
            for i in itens_brutos:
                if not isinstance(i, dict):
                    continue
                texto = (i.get("texto") or "").strip()
                if not texto:
                    continue
                momento = i.get("momento") if i.get("momento") in ("antes", "depois") else "antes"
                itens.append({"texto": texto, "momento": momento})

        imovel.checklist_itens = json.dumps(itens, ensure_ascii=False) if itens else None
        db.session.commit()

        return jsonify({"success": True, "itens": itens})

    except Exception as e:
        current_app.logger.exception("Erro ao salvar o modelo de checklist")
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# EVENTOS NA REGIÃO — Ticketmaster + Google Places + busca manual
# -----------------------------------------------------------------------------
# Diferente dos "Eventos de Precificação" acima (feriados/datas que o
# anfitrião cadastra manualmente pra ajustar preço), isto aqui é uma busca
# de eventos/lugares reais perto do imóvel — pra dar ideia ao anfitrião do
# que vai atrair/lotar a região. Não substitui a precificação, é só
# informativo. Toda a lógica de agregação mora em
# app/services/eventos_service.py (Ticketmaster + Google Places reais,
# Eventbrite/Sympla/Even3 com link de busca manual — ver o levantamento de
# API documentado no topo daquele arquivo).
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/eventos-regionais/<int:imovel_id>")
@login_required
def eventos_regionais(imovel_id: int):
    user_id = get_effective_owner_id()
    imovel = Imovel.query.filter_by(id=imovel_id, user_id=user_id).first()
    if not imovel:
        return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    resultado = eventos_service.agregar_eventos_regionais(imovel)

    if resultado["ticketmaster_configurado"] and (imovel.lat is None or imovel.lng is None):
        resultado["message"] = (
            "Configure a localização (lat/lng) desse imóvel em Imóveis > Editar "
            "pra buscar eventos e lugares próximos."
        )

    return jsonify({"success": True, **resultado})


# ─────────────────────────────────────────────────────────────────────────────
# FORMULÁRIO DE DOCUMENTOS DO HÓSPEDE — visualização do anfitrião
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/documentos-recebidos")
@login_required
def documentos_recebidos():
    """
    Lista os formulários de documentos das estadias do anfitrião — tanto os
    já respondidos (com as respostas do hóspede) quanto os ainda pendentes
    (aguardando o hóspede preencher), mais recentes primeiro.
    """
    from app.models import FormularioDocumentos

    user_id = get_effective_owner_id()
    imoveis = Imovel.query.filter_by(user_id=user_id).all()
    imoveis_map = {im.id: im for im in imoveis}
    if not imoveis_map:
        return jsonify({"success": True, "formularios": []})

    formularios = (
        FormularioDocumentos.query
        .filter(FormularioDocumentos.imovel_id.in_(imoveis_map.keys()))
        .order_by(FormularioDocumentos.updated_at.desc())
        .limit(30)
        .all()
    )

    resultado = []
    for f in formularios:
        im = imoveis_map.get(f.imovel_id)
        estadia = f.estadia
        respostas = []
        for r in (f.respostas or []):
            valor = r.get("valor") or ""
            # Documentos do hóspede (RG/CPF etc.) não ficam mais em
            # /static/uploads (pasta pública) — ver LGPD fix em
            # app/routes/pg_documentos_recebidos.py. Precisa passar pela
            # mesma rota protegida (login + posse do imóvel), senão o link
            # aqui simplesmente não funciona mais.
            url_arquivo = (
                url_for("documentos_recebidos.servir_arquivo", nome_arquivo=valor)
                if r.get("tipo") == "foto" and valor else None
            )
            respostas.append({
                "nome": r.get("nome"),
                "tipo": r.get("tipo"),
                "valor": valor if r.get("tipo") != "foto" else None,
                "url_arquivo": url_arquivo,
            })
        resultado.append({
            "id": f.id,
            "estadia_id": f.estadia_id,
            "imovel": im.titulo if im else "",
            "hospede": estadia.nome_hospede if estadia else "",
            "checkin": estadia.data_checkin.strftime("%d/%m/%Y") if estadia and estadia.data_checkin else "",
            "status": f.status,
            "expira_em": f.expira_em.strftime("%d/%m/%Y") if f.expira_em else None,
            "respondido_em": f.respondido_em.strftime("%d/%m/%Y %H:%M") if f.respondido_em else None,
            "respostas": respostas,
        })

    return jsonify({"success": True, "formularios": resultado})


# ─────────────────────────────────────────────────────────────────────────────
# LEMBRETES / ROTINAS — CRUD
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/lembretes")
@login_required
def listar_lembretes():
    user_id = get_effective_owner_id()
    lembretes = LembreteConfig.query.filter_by(user_id=user_id).all()
    return jsonify({
        "success": True,
        "lembretes": [
            {
                "id": l.id,
                "tipo": l.tipo,
                "titulo": l.titulo,
                "descricao": l.descricao,
                "imovel_id": l.imovel_id,
                "intervalo_dias": l.intervalo_dias,
                "ativo": l.ativo,
            }
            for l in lembretes
        ],
    })


@hub_bp.route("/api/hub/lembretes/salvar", methods=["POST"])
@login_required
def salvar_lembrete():
    user_id = get_effective_owner_id()
    data = request.get_json(silent=True) or {}

    lembrete_id = data.get("id")
    tipo = (data.get("tipo") or "outro").strip()
    titulo = (data.get("titulo") or "").strip() or None
    descricao = (data.get("descricao") or "").strip() or None
    ativo = bool(data.get("ativo", True))

    if tipo not in TIPOS_LEMBRETE:
        return jsonify({"success": False, "message": "Tipo de rotina inválido."}), 400

    if tipo == "outro" and not titulo:
        return jsonify({"success": False, "message": "Descreva o nome dessa rotina personalizada."}), 400

    intervalo_dias = None
    if tipo not in TIPOS_EVENTO:
        try:
            intervalo_dias = int(data.get("intervalo_dias"))
            if intervalo_dias <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Informe a frequência em dias (maior que zero)."}), 400

    imovel_ids_raw = data.get("imovel_ids")
    if imovel_ids_raw is None:
        imovel_ids_raw = [data.get("imovel_id")]
    if not isinstance(imovel_ids_raw, list):
        imovel_ids_raw = [imovel_ids_raw]

    try:
        imovel_ids = [int(i) for i in imovel_ids_raw if i not in (None, "", "todos")]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Imóvel inválido."}), 400

    aplicar_todos = "todos" in imovel_ids_raw or not imovel_ids_raw
    if aplicar_todos:
        imovel_ids = [im.id for im in Imovel.query.filter_by(user_id=user_id).all()]

    if not imovel_ids:
        return jsonify({"success": False, "message": "Selecione ao menos um imóvel."}), 400

    imoveis_validos = {
        im.id: im for im in Imovel.query.filter(
            Imovel.user_id == user_id, Imovel.id.in_(imovel_ids)
        ).all()
    }
    if not imoveis_validos:
        return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    criados = []

    if lembrete_id:
        lembrete = LembreteConfig.query.filter_by(id=lembrete_id, user_id=user_id).first()
        if not lembrete:
            return jsonify({"success": False, "message": "Rotina não encontrada."}), 404

        lembrete.tipo = tipo
        lembrete.titulo = titulo
        lembrete.descricao = descricao
        lembrete.intervalo_dias = intervalo_dias
        lembrete.ativo = ativo
        if imovel_ids:
            lembrete.imovel_id = imovel_ids[0]
        criados.append(lembrete)
    else:
        for im_id in imoveis_validos:
            lembrete = LembreteConfig(
                user_id=user_id,
                imovel_id=im_id,
                tipo=tipo,
                titulo=titulo,
                descricao=descricao,
                intervalo_dias=intervalo_dias,
                ativo=ativo,
            )
            db.session.add(lembrete)
            criados.append(lembrete)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Rotina salva com sucesso.",
        "quantidade": len(criados),
    })


@hub_bp.route("/api/hub/lembretes/toggle/<int:lembrete_id>", methods=["POST"])
@login_required
def toggle_lembrete(lembrete_id: int):
    user_id = get_effective_owner_id()

    lembrete = LembreteConfig.query.filter_by(id=lembrete_id, user_id=user_id).first()
    if not lembrete:
        return jsonify({"success": False, "message": "Rotina não encontrada."}), 404

    lembrete.ativo = not lembrete.ativo
    db.session.commit()

    return jsonify({"success": True, "ativo": lembrete.ativo})


@hub_bp.route("/api/hub/lembretes/excluir/<int:lembrete_id>", methods=["DELETE"])
@login_required
def excluir_lembrete(lembrete_id: int):
    user_id = get_effective_owner_id()

    lembrete = LembreteConfig.query.filter_by(id=lembrete_id, user_id=user_id).first()
    if not lembrete:
        return jsonify({"success": False, "message": "Rotina não encontrada."}), 404

    db.session.delete(lembrete)
    db.session.commit()

    return jsonify({"success": True})


@hub_bp.route("/api/hub/lembretes/excluir-todas", methods=["DELETE"])
@login_required
def excluir_todas_lembretes():
    """Exclui em lote todas as rotinas/lembretes — botão "Excluir todas" da
    aba Rotinas. Respeita os mesmos filtros de imóvel/tipo aplicados na tela
    (querystring `imovel_id`/`tipo`, os mesmos usados por `contexto_rotinas()`
    em pg_rotinas.py), pra só apagar o que a pessoa está de fato vendo na
    lista, e não todas as rotinas de todos os imóveis sem querer.
    """
    user_id = get_effective_owner_id()
    query = LembreteConfig.query.filter_by(user_id=user_id)

    raw_imovel_id = request.args.get("imovel_id")
    if raw_imovel_id:
        query = query.filter(LembreteConfig.imovel_id == int(raw_imovel_id))

    tipo = request.args.get("tipo")
    if tipo and tipo in TIPOS_LEMBRETE:
        query = query.filter(LembreteConfig.tipo == tipo)

    quantidade = query.count()
    query.delete(synchronize_session=False)
    db.session.commit()

    return jsonify({"success": True, "quantidade": quantidade})


# ─────────────────────────────────────────────────────────────────────────────
# EVENTOS DE PRECIFICAÇÃO — CRUD
# ─────────────────────────────────────────────────────────────────────────────

@hub_bp.route("/api/hub/eventos")
@login_required
def listar_eventos_precificacao():
    user_id = get_effective_owner_id()
    eventos = (
        EventoPrecificacao.query
        .filter_by(user_id=user_id)
        .order_by(EventoPrecificacao.data.asc())
        .all()
    )
    return jsonify({
        "success": True,
        "eventos": [
            {
                "id": e.id,
                "titulo": e.titulo,
                "data": e.data.strftime("%Y-%m-%d"),
                "data_fmt": e.data.strftime("%d/%m/%Y"),
                "recorrente": e.recorrente,
                "nivel_impacto": e.nivel_impacto,
                "imovel_id": e.imovel_id,
                "imovel": e.imovel.titulo if e.imovel else "Todos os imóveis",
            }
            for e in eventos
        ],
    })


@hub_bp.route("/api/hub/eventos/salvar", methods=["POST"])
@login_required
def salvar_evento_precificacao():
    user_id = get_effective_owner_id()
    data_req = request.get_json(silent=True) or {}

    evento_id = data_req.get("id")
    titulo = (data_req.get("titulo") or "").strip()
    data_str = (data_req.get("data") or "").strip()
    nivel_impacto = (data_req.get("nivel_impacto") or "media").strip()
    recorrente = bool(data_req.get("recorrente", False))
    imovel_id = data_req.get("imovel_id") or None

    if not titulo:
        return jsonify({"success": False, "message": "Informe um título para o evento."}), 400

    if nivel_impacto not in NIVEIS_IMPACTO:
        return jsonify({"success": False, "message": "Nível de impacto inválido."}), 400

    try:
        data_evento = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data inválida."}), 400

    if imovel_id in (None, "", "todos"):
        imovel_id = None
    else:
        imovel = Imovel.query.filter_by(id=imovel_id, user_id=user_id).first()
        if not imovel:
            return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    if evento_id:
        evento = EventoPrecificacao.query.filter_by(id=evento_id, user_id=user_id).first()
        if not evento:
            return jsonify({"success": False, "message": "Evento não encontrado."}), 404
        evento.titulo = titulo
        evento.data = data_evento
        evento.nivel_impacto = nivel_impacto
        evento.recorrente = recorrente
        evento.imovel_id = imovel_id
    else:
        evento = EventoPrecificacao(
            user_id=user_id,
            imovel_id=imovel_id,
            titulo=titulo,
            data=data_evento,
            nivel_impacto=nivel_impacto,
            recorrente=recorrente,
        )
        db.session.add(evento)

    db.session.commit()

    return jsonify({"success": True, "message": "Evento salvo com sucesso.", "id": evento.id})


@hub_bp.route("/api/hub/precificacao/config", methods=["POST"])
@login_required
def salvar_config_precificacao():
    user_id = get_effective_owner_id()
    user = db.session.get(User, user_id)
    data_req = request.get_json(silent=True) or {}

    def _pct(chave):
        val = data_req.get(chave)
        if val in (None, ""):
            return None
        try:
            val = int(val)
        except (TypeError, ValueError):
            return "erro"
        if val < 0 or val > 200:
            return "erro"
        return val

    alta, media, baixa = _pct("alta"), _pct("media"), _pct("baixa")
    if "erro" in (alta, media, baixa):
        return jsonify({"success": False, "message": "Percentuais devem ser números entre 0 e 200."}), 400

    user.pct_precificacao_alta = alta
    user.pct_precificacao_media = media
    user.pct_precificacao_baixa = baixa
    db.session.commit()

    return jsonify({"success": True, "pct_precificacao": _percentuais_do_usuario(user)})


@hub_bp.route("/api/hub/eventos/excluir/<int:evento_id>", methods=["DELETE"])
@login_required
def excluir_evento_precificacao(evento_id: int):
    user_id = get_effective_owner_id()

    evento = EventoPrecificacao.query.filter_by(id=evento_id, user_id=user_id).first()
    if not evento:
        return jsonify({"success": False, "message": "Evento não encontrado."}), 404

    db.session.delete(evento)
    db.session.commit()

    return jsonify({"success": True})
