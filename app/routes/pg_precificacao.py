"""
app/routes/pg_precificacao.py
Precificação — antes uma página própria (/precificacao), agora uma aba
dentro do Hub do Anfitrião (app/templates/hub_anfitriao.html,
main.hub_anfitriao). `contexto_precificacao()` monta o contexto consumido
pelo partial da aba (app/templates/partials/tab_precificacao.html); a rota
`/precificacao` deste blueprint só redireciona para lá, preservando
bookmarks antigos.

Reúne três sub-recursos distintos que giram em torno de precificação:
  1. Configuração dos percentuais de aumento sugerido por nível de impacto
     (User.pct_precificacao_alta/media/baixa) — salvos via
     POST /api/hub/precificacao/config (endpoint já existente em
     app/routes/hub.py).
  2. CRUD de Eventos de Precificação (EventoPrecificacao) — eventos/datas
     personalizadas que o anfitrião cadastra manualmente para sugerir
     aumento de preço (endpoints já existentes em app/routes/hub.py:
     /api/hub/eventos/salvar e /api/hub/eventos/excluir/<id>).
  3. Oportunidades de Precificação: lista somente-leitura calculada por
     calcular_oportunidades() (app/services/precificacao.py), combinando
     feriados nacionais + Eventos de Precificação — renderizada aqui
     diretamente pelo servidor, sem endpoint dedicado (não é serializado
     em JSON, então o objeto `date` de cada item não é um problema).

Não confundir com "Eventos na Região" (Ticketmaster) — isso é um recurso
totalmente separado e só informativo, que já existe em
GET /api/hub/eventos-regionais/<imovel_id> (app/routes/hub.py); aqui só
consumimos esse endpoint via fetch no client, não reimplementamos nada dele.
"""

from flask import Blueprint, redirect, request, url_for

from app.extensions import db
from app.models import User, Imovel, EventoPrecificacao
from app.models.precificacao import NIVEIS_IMPACTO, PCT_PADRAO
from app.services.precificacao import calcular_oportunidades, _percentuais_do_usuario
from app.utils.auth import login_required, get_effective_owner_id

precificacao_bp = Blueprint("precificacao", __name__)


def contexto_precificacao(owner_id, request_args=None):
    """
    Monta o dict de contexto usado pelo partial da aba "Precificação" do Hub
    do Anfitrião (app/templates/partials/tab_precificacao.html).

    Extraído da antiga view `pagina()` (quando Precificação ainda era uma
    página própria em /precificacao) para poder ser chamado tanto por essa
    rota legada (que agora só redireciona) quanto pela view do Hub
    (main.hub_anfitriao), que renderiza todas as abas server-side de uma vez.

    `request_args` existe só para permitir injeção em testes; em uso normal
    (chamado de dentro de uma view, com contexto de requisição ativo) pode
    ficar None e cai no `flask.request.args` corrente.
    """
    if request_args is None:
        request_args = request.args

    user = db.session.get(User, owner_id)

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).all()

    eventos = (
        EventoPrecificacao.query
        .filter_by(user_id=owner_id)
        .order_by(EventoPrecificacao.data.asc())
        .all()
    )

    # Janela ampla — 365 dias (1 ano), o prazo máximo de antecedência pra
    # reservas. Não são os 30 dias/itens usados no card resumido do Hub —
    # aqui é a aba dedicada, cabe mostrar mais.
    oportunidades = calcular_oportunidades(user, dias_janela=365)[:200] if user else []

    pct_precificacao = _percentuais_do_usuario(user) if user else dict(PCT_PADRAO)

    return {
        "pct_precificacao": pct_precificacao,
        "imoveis": lista_imoveis,
        "eventos": eventos,
        "oportunidades": oportunidades,
        "niveis_impacto": NIVEIS_IMPACTO,
    }


@precificacao_bp.route("/precificacao")
@login_required
def pagina():
    # Precificação deixou de ser uma página própria e virou uma aba dentro do
    # Hub do Anfitrião — mantemos essa rota só para não quebrar bookmarks/links
    # antigos apontando para /precificacao.
    return redirect(url_for("main.hub_anfitriao", tab="precificacao"))
