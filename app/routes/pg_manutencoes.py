"""
app/routes/pg_manutencoes.py
Página dedicada de Manutenções — parte do desmembramento do antigo Hub do
Anfitrião (Task de redesign do Hub): antes tudo vivia amontoado numa página
só, agora cada assunto tem a sua.

Diferente de Limpezas, Manutenções (HubTarefa.tipo == "manutencao") PODEM
ser criadas manualmente pelo anfitrião — aqui a página oferece o botão
"Registrar Manutenção", que chama o endpoint já existente
POST /api/hub/manutencao (app/routes/hub.py), além de listar, filtrar,
editar, concluir/reabrir e excluir.
"""

from flask import Blueprint, redirect, request, url_for

from app.models import HubTarefa
from app.models.imovel import Imovel
from app.utils import login_required

manutencoes_bp = Blueprint("manutencoes", __name__)


def contexto_manutencoes(owner_id, request_args=None):
    """Monta o dicionário de contexto usado pelo template/partial de Manutenções.

    `request_args` é opcional e aceita qualquer dict-like (ex.: Flask
    `request.args`) com os filtros `imovel_id` e `status`. Se omitido, lê
    `flask.request.args` diretamente — útil tanto para a rota própria
    (`/manutencoes`) quanto para a rota do Hub, que pode chamar esta função
    para montar a aba "Manutenções" dentro de `hub_anfitriao()`.
    """
    if request_args is None:
        request_args = request.args

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).all()

    query = HubTarefa.query.filter_by(user_id=owner_id, tipo="manutencao")

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


@manutencoes_bp.route("/manutencoes")
@login_required
def pagina():
    # Página própria descontinuada — Manutenções foi unida com Limpezas e
    # Reposição numa aba só ("tarefas") dentro do Hub do Anfitrião. Mantemos
    # a rota só para não quebrar favoritos/links antigos.
    return redirect(url_for("main.hub_anfitriao", tab="tarefas"))
