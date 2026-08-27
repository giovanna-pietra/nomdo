"""
app/routes/pg_checklists.py
Página dedicada de Checklists de Hospedagem — parte do desmembramento do
antigo Hub do Anfitrião: antes tudo vivia amontoado numa página só, agora
cada assunto tem a sua.

Duas coisas distintas convivem aqui, ambas chamadas de "checklist":

  1) MODELO (por imóvel, reutilizável) — `Imovel.checklist_itens`, editado
     no card "Editor de Modelo". Fonte da verdade / fallback padrão vivem
     em app/routes/hub.py (`_checklist_template`, `DEFAULT_CHECKLIST_ITENS`)
     — reaproveitados aqui em vez de duplicados. Salva via o endpoint que já
     existe em hub.py: POST /api/hub/checklist-modelo/<imovel_id>.

  2) PROGRESSO de uma ESTADIA específica — `Estadia.checklist_status`,
     exibido no card "Checklist da Estadia Atual" com checkboxes. Toggle via
     o endpoint que já existe em hub.py: POST /api/hub/checklist/toggle.

Esta rota só faz GET (server-render) — não existe (nem precisa existir) um
GET /api/hub/checklist-modelo, o template do imóvel selecionado é montado
direto aqui em Python e passado pro Jinja.
"""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from app.models import Imovel, Estadia
from app.routes.hub import (
    JANELA_LIMPEZA_RETROATIVA,
    _checklist_template,
    _checklist_para_estadia,
)
from app.utils import login_required, get_effective_owner_id

checklists_bp = Blueprint("checklists", __name__)


def _estadia_atual(imovel_id: int, owner_id: int, hoje: date):
    """
    Escolhe QUAL estadia representa "a estadia atual" do imóvel selecionado,
    pra mostrar o progresso do checklist de um único hóspede por vez (em vez
    de misturar o "antes" de um hóspede futuro com o "depois" de outro que já
    saiu, como o card único do antigo Hub fazia). Prioridade:

      1) uma estadia em andamento agora (o período cobre hoje);
      2) senão, a próxima estadia futura (check-in ainda não aconteceu);
      3) senão, a última que fez checkout dentro da janela retroativa de
         limpeza (mesma janela do motor de lembretes, JANELA_LIMPEZA_RETROATIVA)
         — pra ainda dar tempo de fechar o checklist de "depois" antes de a
         limpeza ser dada como esquecida.

    Retorna (estadia | None, situacao: str).
    """
    em_andamento = (
        Estadia.query
        .filter(
            Estadia.imovel_id == imovel_id,
            Estadia.user_id == owner_id,
            Estadia.status.notin_(["cancelada", "bloqueio"]),
            Estadia.data_checkin <= hoje,
            Estadia.data_checkout >= hoje,
        )
        .order_by(Estadia.data_checkin.desc())
        .first()
    )
    if em_andamento:
        return em_andamento, "em_andamento"

    proxima = (
        Estadia.query
        .filter(
            Estadia.imovel_id == imovel_id,
            Estadia.user_id == owner_id,
            Estadia.status.in_(["confirmada", "em_andamento"]),
            Estadia.data_checkin >= hoje,
        )
        .order_by(Estadia.data_checkin.asc())
        .first()
    )
    if proxima:
        return proxima, "proxima"

    limite = hoje - timedelta(days=JANELA_LIMPEZA_RETROATIVA)
    recente = (
        Estadia.query
        .filter(
            Estadia.imovel_id == imovel_id,
            Estadia.user_id == owner_id,
            Estadia.status.notin_(["cancelada", "bloqueio"]),
            Estadia.data_checkout <= hoje,
            Estadia.data_checkout >= limite,
        )
        .order_by(Estadia.data_checkout.desc())
        .first()
    )
    if recente:
        return recente, "recente"

    return None, ""


def contexto_checklists(owner_id, request_args=None, ocultar_dados_reserva=False):
    """
    Monta o dict de contexto usado pelo template da aba de Checklists
    (partials/tab_checklists.html). Extraído de `pagina()` pra poder ser
    chamado tanto pela rota antiga (`/checklists`, hoje só um redirect) quanto
    pela view do Hub do Anfitrião (`main.hub_anfitriao`), que monta o
    contexto de todas as abas de uma vez.

    `request_args` é o mapping de query string a usar pro filtro `imovel_id`
    (tipicamente `request.args`). Se `None`, cai pro `flask.request.args` do
    contexto de requisição corrente — funciona tanto quando chamado a partir
    desta blueprint quanto de dentro de `main.hub_anfitriao()`, já que
    `request` é sempre o da requisição ativa, não da blueprint que o define.
    """
    if request_args is None:
        request_args = request.args

    hoje = date.today()

    imoveis = Imovel.query.filter_by(user_id=owner_id).order_by(Imovel.titulo.asc()).all()

    imovel_id = request_args.get("imovel_id", type=int)
    imovel_selecionado = None
    if imovel_id:
        imovel_selecionado = next((im for im in imoveis if im.id == imovel_id), None)
    if not imovel_selecionado and imoveis:
        imovel_selecionado = imoveis[0]

    modelo_antes = []
    modelo_depois = []
    estadia_atual = None

    if imovel_selecionado:
        template = _checklist_template(imovel_selecionado)
        modelo_antes = [i for i in template if i["momento"] == "antes"]
        modelo_depois = [i for i in template if i["momento"] == "depois"]

        estadia, situacao = _estadia_atual(imovel_selecionado.id, owner_id, hoje)
        if estadia:
            estadia_atual = {
                "situacao": situacao,
                "antes": _checklist_para_estadia(estadia, imovel_selecionado, "antes", ocultar_dados_reserva),
                "depois": _checklist_para_estadia(estadia, imovel_selecionado, "depois", ocultar_dados_reserva),
            }

    return {
        "imoveis": imoveis,
        "imovel_selecionado": imovel_selecionado,
        "modelo_antes": modelo_antes,
        "modelo_depois": modelo_depois,
        "estadia_atual": estadia_atual,
    }


@checklists_bp.route("/checklists")
@login_required
def pagina():
    return redirect(url_for("main.hub_anfitriao", tab="checklists"))
