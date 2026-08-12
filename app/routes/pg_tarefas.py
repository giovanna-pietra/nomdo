"""
app/routes/pg_tarefas.py
Aba unificada "Cuidados do Imóvel" — antes eram duas abas separadas
(Limpezas e Manutenções); a pedido do anfitrião, foram unidas numa só,
junto com os itens avulsos de "comprar"/"repor" (que antes só apareciam
num atalho da aba Hoje, sem um lugar próprio pra gerenciar) e um tipo
"personalizado" pra qualquer tarefa avulsa que não se encaixe nos outros.

Os tipos de HubTarefa cobertos aqui: "limpeza_checkout", "manutencao",
"comprar", "repor", "personalizado", além dos tipos "de regra" que só
existem como Rotina (pilha_fechadura/eletronicos/cafe/papel_higienico/
outro) — quando uma Rotina desses tipos vence, processar_lembretes() (em
app/routes/hub.py) cria uma HubTarefa com esse mesmo tipo, e ela precisa
aparecer aqui pra virar uma ação concreta (senão fica "perdida": não conta
mais como vencida em Prioridades do Dia depois de virar tarefa, e sem
estar na lista de tipos operacionais também não aparece em lugar nenhum).
Só ficam de fora os tipos guiados por checklist de hóspede
(checklist_antes/checklist_depois), que têm tela própria (aba Checklists).
Todos usam o mesmo endpoint de criação já existente (POST
/api/hub/manutencao, em app/routes/hub.py) — a diferença entre eles é só
o valor de `tipo` enviado.
"""

from flask import Blueprint, redirect, request, url_for

from app.models import HubTarefa
from app.models.hub import TIPOS_LEMBRETE
from app.models.imovel import Imovel
from app.utils import login_required

tarefas_bp = Blueprint("tarefas", __name__)

TIPOS_OPERACIONAIS = (
    "limpeza_checkout", "manutencao", "comprar", "repor", "personalizado",
    "pilha_fechadura", "eletronicos", "cafe", "papel_higienico", "outro",
)

# Todos os tipos relevantes pra essa aba (TIPOS_LEMBRETE tem só mais os
# guiados por checklist de hóspede — checklist_antes/checklist_depois —
# que não fazem sentido aqui, têm tela própria).
TIPOS_LEMBRETE_OPERACIONAIS = {k: TIPOS_LEMBRETE[k] for k in TIPOS_OPERACIONAIS}


def contexto_tarefas(owner_id, request_args=None):
    """Monta o dicionário de contexto usado pelo template/partial da aba unificada.

    `request_args` é opcional e aceita qualquer dict-like (ex.: Flask
    `request.args`) com os filtros `imovel_id` e `tipo`. Se omitido, lê
    `flask.request.args` diretamente — útil tanto para as rotas
    descontinuadas (`/limpezas`, `/manutencoes`) quanto para a rota do Hub,
    que chama esta função pra montar a aba dentro de `hub_anfitriao()`.

    Pendentes e concluídas vêm em listas separadas (em vez de um filtro de
    "status") — a página mostra as pendentes na lista principal e as
    concluídas num "Histórico" logo abaixo, sempre visível.
    """
    if request_args is None:
        request_args = request.args

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).all()

    query = HubTarefa.query.filter_by(user_id=owner_id).filter(
        HubTarefa.tipo.in_(TIPOS_OPERACIONAIS)
    )

    raw_imovel_id = request_args.get("imovel_id")
    imovel_id = int(raw_imovel_id) if raw_imovel_id else None
    if imovel_id:
        query = query.filter(HubTarefa.imovel_id == imovel_id)

    tipo = request_args.get("tipo")  # um de TIPOS_OPERACIONAIS | None (todos)
    if tipo in TIPOS_OPERACIONAIS:
        query = query.filter(HubTarefa.tipo == tipo)
    else:
        tipo = ""

    tarefas_pendentes = (
        query.filter(HubTarefa.concluida.is_(False))
        .order_by(HubTarefa.data_prevista.asc().nullslast(), HubTarefa.created_at.desc())
        .all()
    )
    tarefas_concluidas = (
        query.filter(HubTarefa.concluida.is_(True))
        .order_by(HubTarefa.created_at.desc())
        .all()
    )

    return {
        "tarefas_pendentes": tarefas_pendentes,
        "tarefas_concluidas": tarefas_concluidas,
        "imoveis": lista_imoveis,
        "filtro_imovel_id": imovel_id,
        "filtro_tipo": tipo,
        "tipos_lembrete": TIPOS_LEMBRETE_OPERACIONAIS,
    }


@tarefas_bp.route("/tarefas")
@login_required
def pagina():
    return redirect(url_for("main.hub_anfitriao", tab="tarefas"))
