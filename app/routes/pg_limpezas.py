"""
app/routes/pg_limpezas.py
Página dedicada de Limpezas — parte do desmembramento do antigo Hub do
Anfitrião (Task de redesign do Hub): antes tudo vivia amontoado numa página
só, agora cada assunto tem a sua.

Limpezas (HubTarefa.tipo == "limpeza_checkout") são sempre geradas
automaticamente pelo motor de lembretes (ver `processar_lembretes` em
app/routes/hub.py, disparado a cada checkout de Estadia) — não existe (nem
deveria existir) um botão de "Nova Limpeza" aqui: criar uma tarefa de
limpeza manualmente não corresponde a nenhum evento real do sistema. Esta
página só lista, filtra, conclui/reabre e exclui.
"""

from flask import Blueprint, redirect, request, url_for

from app.models import HubTarefa
from app.models.imovel import Imovel
from app.utils import login_required, get_effective_owner_id

limpezas_bp = Blueprint("limpezas", __name__)


def contexto_limpezas(owner_id, request_args=None):
    """Monta o dicionário de contexto usado pelo template/partial de Limpezas.

    `request_args` é opcional e aceita qualquer dict-like (ex.: Flask
    `request.args`) com os filtros `imovel_id` e `status`. Se omitido, lê
    `flask.request.args` diretamente — útil tanto para a rota própria
    (`/limpezas`) quanto para a rota do Hub, que pode chamar esta função
    para montar a aba "Limpezas" dentro de `hub_anfitriao()`.
    """
    if request_args is None:
        request_args = request.args

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).all()

    query = HubTarefa.query.filter_by(user_id=owner_id, tipo="limpeza_checkout")

    raw_imovel_id = request_args.get("imovel_id")
    imovel_id = int(raw_imovel_id) if raw_imovel_id else None
    if imovel_id:
        query = query.filter(HubTarefa.imovel_id == imovel_id)

    status = request_args.get("status")  # "pendente" | "concluida" | None (todas)
    if status == "pendente":
        query = query.filter(HubTarefa.concluida.is_(False))
    elif status == "concluida":
        query = query.filter(HubTarefa.concluida.is_(True))

    tarefas = query.order_by(
        HubTarefa.concluida.asc(), HubTarefa.created_at.desc()
    ).all()

    return {
        "tarefas": tarefas,
        "imoveis": lista_imoveis,
        "filtro_imovel_id": imovel_id,
        "filtro_status": status or "",
    }


@limpezas_bp.route("/limpezas")
@login_required
def pagina():
    # Página própria descontinuada — Limpezas foi unida com Manutenções e
    # Reposição numa aba só ("tarefas") dentro do Hub do Anfitrião. Mantemos
    # a rota só para não quebrar favoritos/links antigos.
    return redirect(url_for("main.hub_anfitriao", tab="tarefas"))
