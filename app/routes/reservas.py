import calendar
import os

from decimal import Decimal
from datetime import datetime, date

from dotenv import load_dotenv

from flask import (
    Blueprint,
    render_template,
    session,
)

from app.extensions import db
from app.models import User, Imovel, Estadia
from app.utils import login_required, formatar_nome_exibicao

load_dotenv()

# NOTA: este blueprint mantém o nome histórico "reservas" (e o arquivo
# reservas.py) só pra não quebrar os `url_for("reservas.dashboard")`
# espalhados pelos templates — a feature de "Reserva" (agenda de viagens
# pessoais do hóspede, sem relação com os imóveis) foi removida por
# completo. O que resta aqui é só a rota /dashboard do anfitrião.
reservas_bp = Blueprint("reservas", __name__)


# =========================================================
# DASHBOARD
# =========================================================
# (O paywall agora é feito pelo gate global em app/__init__.py —
#  ver app/routes/pagamento.py — em vez de um decorator por rota. O
#  decorator antigo aqui nunca funcionou de verdade: por causa da ordem
#  dos decorators, o Flask registrava a rota com a função já sem ele.)
@reservas_bp.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id)
    hoje = date.today()

    # =====================================================
    # CONSULTAS BASE
    # =====================================================
    imoveis = Imovel.query.filter_by(user_id=user.id).all()

    # =====================================================
    # ESTATÍSTICAS DE ANFITRIÃO (Imóveis + Estadias)
    # -----------------------------------------------------
    # Todas as métricas do dashboard vêm de Imovel + Estadia (o registro
    # real de hospedagem feito em cada imóvel, tela "Imóveis"). O antigo
    # modelo "Reserva" (agenda de viagens pessoais do usuário como
    # hóspede em OUTROS lugares) foi removido — não tinha relação com os
    # imóveis cadastrados no Nomdo.
    # =====================================================
    imovel_ids     = [i.id for i in imoveis]
    imovel_titulos = {i.id: i.titulo for i in imoveis}

    estadias_host = (
        Estadia.query.filter(Estadia.imovel_id.in_(imovel_ids)).all()
        if imovel_ids else []
    )

    dias_no_mes      = calendar.monthrange(hoje.year, hoje.month)[1]
    primeiro_dia_mes = hoje.replace(day=1)
    ultimo_dia_mes   = hoje.replace(day=dias_no_mes)

    reservas_ativas_host  = 0
    checkins_hoje         = 0
    faturamento_total      = Decimal("0.00")
    faturamento_mes        = Decimal("0.00")
    dias_ocupados_mes      = 0
    estadias_por_imovel    = {}   # imovel_id -> nº de estadias válidas (demanda)
    faturamento_por_imovel = {}   # imovel_id -> receita bruta acumulada

    for e in estadias_host:
        if e.status == "cancelada":
            continue

        # Bloqueio operacional ocupa a agenda (entra na ocupação abaixo),
        # mas não é hospedagem paga: não conta como "reserva ativa", não
        # entra em receita e não entra nos rankings de imóvel mais/menos
        # procurado.
        if e.status != "bloqueio":
            if e.data_checkin and e.data_checkout and e.data_checkin <= hoje <= e.data_checkout:
                reservas_ativas_host += 1
            if e.data_checkin == hoje:
                checkins_hoje += 1

            # Faturamento usa o valor LÍQUIDO (o que de fato entra pro
            # anfitrião depois da taxa da plataforma) — não o bruto (o que
            # o hóspede pagou). Mesma convenção usada em Finanças e no
            # Dashboard do Proprietário; usar o bruto aqui fazia o cartão
            # de "Faturamento" mostrar valor mesmo quando o líquido
            # registrado era 0 (nenhuma receita de verdade pro anfitrião).
            valor_estadia = Decimal(str(e.valor_liquido or 0))
            faturamento_total += valor_estadia
            estadias_por_imovel[e.imovel_id]    = estadias_por_imovel.get(e.imovel_id, 0) + 1
            faturamento_por_imovel[e.imovel_id] = faturamento_por_imovel.get(e.imovel_id, Decimal("0.00")) + valor_estadia

        if (e.data_checkin and e.data_checkout
                and e.data_checkin <= ultimo_dia_mes and e.data_checkout >= primeiro_dia_mes):
            inicio_ef = max(e.data_checkin,  primeiro_dia_mes)
            fim_ef    = min(e.data_checkout, ultimo_dia_mes)
            dias_ocupados_mes += max(0, (fim_ef - inicio_ef).days)
            if e.status != "bloqueio":
                faturamento_mes += Decimal(str(e.valor_liquido or 0))

    total_imoveis = len(imoveis)

    # Dashboard "desbloqueia" (mostra métricas de verdade) só quando a
    # pessoa já tem pelo menos 1 imóvel E pelo menos 1 estadia registrada
    # — só com o imóvel, os números viravam uma parede de zero/R$ 0,00,
    # o que dava a impressão de "não ter dashboard nenhum". Com imóvel
    # mas sem estadia ainda, mostramos uma tela própria de onboarding
    # (ver dashboard.html) em vez do empty-state genérico de "sem imóvel".
    tem_estadias = bool(estadias_host)
    dashboard_desbloqueado = total_imoveis > 0 and tem_estadias

    media_ocupacao = 0.0
    if total_imoveis and dias_no_mes:
        media_ocupacao = round(min(100, (dias_ocupados_mes / (dias_no_mes * total_imoveis)) * 100), 1)

    revpar = (faturamento_mes / total_imoveis) if total_imoveis else Decimal("0.00")

    # Ranking de procura: precisa considerar TODOS os imóveis do usuário,
    # inclusive os que ainda não tiveram nenhuma estadia (contagem 0) —
    # senão um imóvel sem reservas nunca aparece como "menos procurado"
    # (ele simplesmente não tinha entrada no dict e ficava de fora do
    # min()/max()). Sem estadias suficientes pra formar um ranking, deixa em
    # branco (não mostra o texto "Sem dados", que ficava esquisito no card).
    contagem_todos_imoveis = {i.id: estadias_por_imovel.get(i.id, 0) for i in imoveis}

    imovel_mais_procurado  = ""
    imovel_menos_procurado = ""
    if contagem_todos_imoveis and any(qtd > 0 for qtd in contagem_todos_imoveis.values()):
        mais_id = max(contagem_todos_imoveis, key=contagem_todos_imoveis.get)
        imovel_mais_procurado = imovel_titulos.get(mais_id, "")
        if len(contagem_todos_imoveis) > 1:
            menos_id = min(contagem_todos_imoveis, key=contagem_todos_imoveis.get)
            imovel_menos_procurado = imovel_titulos.get(menos_id, "")

    # =====================================================
    # FORMATAÇÃO MONETÁRIA BRASILEIRA (R$ 1.234,56)
    # =====================================================
    def formatar_moeda(valor):
        return "{:,.2f}".format(valor).replace(",", "X").replace(".", ",").replace("X", ".")

    stats = {
        "total_imoveis": total_imoveis,
        "reservas_ativas": reservas_ativas_host,
        "checkins_hoje": checkins_hoje,
        "faturamento": formatar_moeda(faturamento_total),
        "media_avaliacao": "5.0",

        "faturamento_total": formatar_moeda(faturamento_total),
        "media_ocupacao": media_ocupacao,
        "imovel_mais_procurado": imovel_mais_procurado,
        "imovel_menos_procurado": imovel_menos_procurado,
        "revpar": formatar_moeda(revpar),

        "imovel_destaque": imoveis[0].titulo if imoveis else "Nenhum"
    }

    # ── Gráficos: sempre por imóvel (bate com os títulos dos cards
    #    "Faturamento por Imóvel" / "Estadias por Imóvel"). ──
    faturamento_chart_labels = [i.titulo for i in imoveis]
    faturamento_chart_values = [
        float(faturamento_por_imovel.get(i.id, Decimal("0.00"))) for i in imoveis
    ]
    estadias_chart_labels = faturamento_chart_labels
    estadias_chart_values = [estadias_por_imovel.get(i.id, 0) for i in imoveis]

    return render_template(
        "dashboard.html",
        user=user,
        nome_usuario=formatar_nome_exibicao(user.nome),
        stats=stats,
        tem_imoveis=total_imoveis > 0,
        tem_estadias=tem_estadias,
        dashboard_desbloqueado=dashboard_desbloqueado,

        faturamento_chart={
            "labels": faturamento_chart_labels,
            "values": faturamento_chart_values
        },

        estadias_chart={
            "labels": estadias_chart_labels,
            "values": estadias_chart_values
        },

        conteudo_existe=True
    )
