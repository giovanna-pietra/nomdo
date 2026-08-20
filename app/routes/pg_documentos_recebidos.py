"""
app/routes/pg_documentos_recebidos.py
Página dedicada de Documentos Recebidos — parte do desmembramento do antigo
Hub do Anfitrião (Task de redesign do Hub): antes tudo vivia amontoado numa
página só, agora cada assunto tem a sua.

Documentos Recebidos é só uma tela de acompanhamento/gestão: lista os
formulários de documentos (FormularioDocumentos) das estadias do anfitrião,
tanto os já respondidos (com as respostas do hóspede — fotos e textos) quanto
os ainda pendentes (aguardando o hóspede preencher). É somente leitura — o
envio do link é automático (ver app/services/documentos_service.py, disparado
N dias antes do check-in, envio único) e não existe nenhum mecanismo de
reenvio/cancelamento manual exposto em lugar nenhum do sistema hoje, então
esta página não inventa um botão pra isso.
"""
from __future__ import annotations

import os

from flask import (
    Blueprint, render_template, request, url_for,
    send_from_directory, current_app, abort,
)

from app.models import FormularioDocumentos
from app.models.imovel import Imovel
from app.utils.auth import login_required, get_effective_owner_id

documentos_recebidos_bp = Blueprint("documentos_recebidos", __name__)

LIMITE_LISTA = 200


@documentos_recebidos_bp.route("/documentos-recebidos")
@login_required
def pagina():
    owner_id = get_effective_owner_id()

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).all()
    imoveis_map = {im.id: im for im in lista_imoveis}

    filtro_imovel_id = request.args.get("imovel_id", type=int)
    filtro_status = request.args.get("status") or ""  # "pendente" | "respondido" | "" (todos)

    formularios = []
    if imoveis_map:
        query = FormularioDocumentos.query.filter(
            FormularioDocumentos.imovel_id.in_(imoveis_map.keys())
        )

        if filtro_imovel_id:
            query = query.filter(FormularioDocumentos.imovel_id == filtro_imovel_id)

        if filtro_status in ("pendente", "respondido"):
            query = query.filter(FormularioDocumentos.status == filtro_status)

        formularios_db = (
            query.order_by(FormularioDocumentos.updated_at.desc())
            .limit(LIMITE_LISTA)
            .all()
        )

        for f in formularios_db:
            im = imoveis_map.get(f.imovel_id)
            estadia = f.estadia
            respostas = []
            for r in (f.respostas or []):
                valor = r.get("valor") or ""
                url_arquivo = (
                    url_for("documentos_recebidos.servir_arquivo", nome_arquivo=valor)
                    if r.get("tipo") == "foto" and valor else None
                )
                respostas.append({
                    "nome": r.get("nome"),
                    "tipo": r.get("tipo"),
                    "obrigatorio": r.get("obrigatorio"),
                    "valor": valor if r.get("tipo") != "foto" else None,
                    "url_arquivo": url_arquivo,
                })
            formularios.append({
                "id": f.id,
                "estadia_id": f.estadia_id,
                "imovel_id": f.imovel_id,
                "imovel": im.titulo if im else "",
                "hospede": estadia.nome_hospede if estadia else "",
                "checkin": estadia.data_checkin.strftime("%d/%m/%Y") if estadia and estadia.data_checkin else "",
                "status": f.status,
                "expira_em": f.expira_em.strftime("%d/%m/%Y") if f.expira_em else None,
                "respondido_em": f.respondido_em.strftime("%d/%m/%Y %H:%M") if f.respondido_em else None,
                "respostas": respostas,
            })

    return render_template(
        "documentos_recebidos.html",
        formularios=formularios,
        imoveis=lista_imoveis,
        filtro_imovel_id=filtro_imovel_id,
        filtro_status=filtro_status,
    )


@documentos_recebidos_bp.route("/documentos-recebidos/arquivo/<string:nome_arquivo>")
@login_required
def servir_arquivo(nome_arquivo):
    """
    Serve um documento (foto de RG/CPF, do pet etc.) só se ele pertencer a
    um FormularioDocumentos de um imóvel do anfitrião logado (ou de quem
    ele efetivamente representa — ver get_effective_owner_id).

    Substitui o link antigo (/static/uploads/<arquivo>), que era público:
    qualquer um com a URL exata via, sem exigir login. Esses documentos
    ficam em UPLOAD_FOLDER_DOCUMENTOS, fora de app/static, então essa rota
    é o único jeito de acessá-los.
    """
    owner_id = get_effective_owner_id()

    imoveis_ids = [
        im.id for im in Imovel.query.filter_by(user_id=owner_id).all()
    ]
    if not imoveis_ids:
        abort(404)

    # os.path.basename bloqueia tentativa de path traversal ("../../etc").
    nome_seguro = os.path.basename(nome_arquivo)

    formularios = FormularioDocumentos.query.filter(
        FormularioDocumentos.imovel_id.in_(imoveis_ids)
    ).all()

    pertence_ao_anfitriao = any(
        r.get("tipo") == "foto" and (r.get("valor") or "") == nome_seguro
        for f in formularios
        for r in (f.respostas or [])
    )
    if not pertence_ao_anfitriao:
        abort(404)

    return send_from_directory(
        current_app.config["UPLOAD_FOLDER_DOCUMENTOS"], nome_seguro
    )
