"""
app/routes/main.py
Blueprint principal: dashboard, configurações, finanças.
"""

from datetime import datetime, timedelta
import json
import traceback

from flask import Blueprint, current_app, jsonify, render_template, redirect, url_for, session, request, flash

from app.extensions import db
from app.models      import User
from app.models.imovel import Imovel
from app.models.estadia import Estadia
from app.utils       import login_required, formatar_nome_exibicao, get_effective_owner_id
from app.models.financas import Financeiro, FinanceiroDespesa, DespesaGeral

main_bp = Blueprint("main", __name__)


# ── Sistema genérico de "período" do dashboard do proprietário ──────────
# Suporta 4 granularidades (mês / trimestre / semestre / ano), todas
# tratadas com a mesma lógica de índice — evita ter que escrever regras
# ad-hoc de virada de ano pra cada granularidade separadamente.
MESES_POR_UNIDADE = {"mes": 1, "trimestre": 3, "semestre": 6, "ano": 12}
ROTULO_PERIODO = {"mes": "mês", "trimestre": "trimestre", "semestre": "semestre", "ano": "ano"}


def _unidades_no_ano(periodo: str) -> int:
    """Quantas 'unidades' desse período cabem em um ano (12/4/2/1)."""
    return 12 // MESES_POR_UNIDADE[periodo]


def _periodo_atual(periodo: str, hoje: datetime) -> tuple:
    """(ano, unidade) correspondente a hoje, pra essa granularidade."""
    meses_por_unidade = MESES_POR_UNIDADE[periodo]
    unidade = ((hoje.month - 1) // meses_por_unidade) + 1
    return hoje.year, unidade


def _parse_valor_periodo(periodo: str, valor: str, hoje: datetime) -> tuple:
    """
    Decodifica o parâmetro ?valor= (formato depende do período: 'YYYY-MM'
    pra mês, 'YYYY-Tn' trimestre, 'YYYY-Sn' semestre, 'YYYY' ano). Qualquer
    formato inválido cai de volta no período atual, em vez de quebrar.
    """
    try:
        if periodo == "mes":
            ano_s, mes_s = valor.split("-", 1)
            ano, unidade = int(ano_s), int(mes_s)
            if not (1 <= unidade <= 12):
                raise ValueError
        elif periodo == "trimestre":
            ano_s, u_s = valor.split("-T", 1)
            ano, unidade = int(ano_s), int(u_s)
            if not (1 <= unidade <= 4):
                raise ValueError
        elif periodo == "semestre":
            ano_s, u_s = valor.split("-S", 1)
            ano, unidade = int(ano_s), int(u_s)
            if not (1 <= unidade <= 2):
                raise ValueError
        elif periodo == "ano":
            ano, unidade = int(valor), 1
        else:
            raise ValueError
        return ano, unidade
    except (ValueError, AttributeError, TypeError):
        return _periodo_atual(periodo, hoje)


def _formatar_valor_periodo(periodo: str, ano: int, unidade: int) -> str:
    if periodo == "mes":
        return f"{ano:04d}-{unidade:02d}"
    if periodo == "trimestre":
        return f"{ano:04d}-T{unidade}"
    if periodo == "semestre":
        return f"{ano:04d}-S{unidade}"
    return f"{ano:04d}"


def _intervalo_periodo(periodo: str, ano: int, unidade: int):
    """(primeiro_dia, ultimo_dia) como date(), cobrindo a unidade inteira."""
    meses_por_unidade = MESES_POR_UNIDADE[periodo]
    mes_inicio = (unidade - 1) * meses_por_unidade + 1
    primeiro_dia = datetime(ano, mes_inicio, 1)

    mes_fim_exclusive = mes_inicio + meses_por_unidade
    if mes_fim_exclusive > 12:
        proximo = datetime(ano + 1, mes_fim_exclusive - 12, 1)
    else:
        proximo = datetime(ano, mes_fim_exclusive, 1)

    ultimo_dia = (proximo - timedelta(days=1)).date()
    return primeiro_dia.date(), ultimo_dia


MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _label_periodo(periodo: str, ano: int, unidade: int) -> str:
    # Traduzido via t_flash — a chave de tradução é o texto em português
    # já formatado (com %(ano)s como placeholder), então pt-br sai idêntico
    # ao comportamento antigo (f-string pura) e en/es pegam a versão traduzida.
    from app.utils.i18n import t_flash

    if periodo == "mes":
        # Nome do mês por dicionário fixo (em vez de strftime + locale do
        # servidor, que pode vir em inglês ou minúsculo dependendo do SO)
        # pra sempre sair "Julho de 2026", com maiúscula, certo.
        mes_nome = t_flash(MESES_PT[unidade])
        return t_flash("%(mes)s de %(ano)s", mes=mes_nome, ano=ano)
    if periodo == "trimestre":
        return t_flash(f"{unidade}º Trimestre de %(ano)s", ano=ano)
    if periodo == "semestre":
        return t_flash(f"{unidade}º Semestre de %(ano)s", ano=ano)
    return t_flash("Ano de %(ano)s", ano=ano)


def _navegacao_periodo(periodo: str, ano: int, unidade: int) -> tuple:
    """
    (valor_anterior, valor_seguinte) — calculado via índice contínuo
    (ano * qtd_unidades_no_ano + (unidade - 1)) pra virada de ano
    funcionar igual pras 4 granularidades, sem branch por tipo.
    """
    qtd = _unidades_no_ano(periodo)
    idx = ano * qtd + (unidade - 1)

    ano_ant, u_ant0 = divmod(idx - 1, qtd)
    ano_seg, u_seg0 = divmod(idx + 1, qtd)

    valor_anterior = _formatar_valor_periodo(periodo, ano_ant, u_ant0 + 1)
    valor_seguinte = _formatar_valor_periodo(periodo, ano_seg, u_seg0 + 1)
    return valor_anterior, valor_seguinte


def _ctx(user: User) -> dict:
    """Contexto padrão compartilhado entre as páginas principais."""
    return {
        "user":               user,
        "nome_usuario":       formatar_nome_exibicao(user.nome),
        "nome_completo":      user.nome,
        "categoria_usuario":  user.categoria,
    }


def _despesa_geral_para_lancamento(despesa: DespesaGeral, imovel_titulo: str) -> dict:
    """
    Serializa uma DespesaGeral no MESMO formato dos lançamentos de
    Financeiro/Estadia (bruto/liqPlat/despesas[]), pra ela poder entrar
    na tabela única de Finanças como uma linha marcada "Despesa Geral"
    (sem precisar criar uma "receita" fake de R$ 0,00 só pra pendurar
    o custo em algum lugar).
    """
    # A categoria já É a descrição da despesa (IPTU, Condomínio...);
    # só cai no texto livre (nome) quando a categoria é "Outro".
    rotulo = despesa.categoria if (despesa.categoria and despesa.categoria != "Outro") else despesa.nome

    return {
        "id":          despesa.id,
        "tipo":        "despesa_geral",
        "editavel":    True,
        "imovel_id":   despesa.imovel_id,
        "imovel":      imovel_titulo,
        "status":      None,
        "site":        None,
        "descricao":   rotulo,
        "entrada":     despesa.data.strftime("%Y-%m-%d") if despesa.data else "",
        "saida":       "",
        "bruto":       0.0,
        "liqPlat":     0.0,
        "data":        despesa.data.strftime("%Y-%m-%d") if despesa.data else "",
        "categoria":   despesa.categoria or "",
        "observacoes": despesa.observacoes or "",
        "despesas": [
            {"nome": rotulo, "valor": float(despesa.valor or 0)}
        ],
    }


@main_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("reservas.dashboard"))
    return render_template("index.html")


@main_bp.route("/site")
def site():
    return redirect(url_for("main.index"))


@main_bp.route("/idioma/<codigo>")
def trocar_idioma(codigo):
    """
    Troca de idioma pras páginas PÚBLICAS (login, cadastro, guia do
    hóspede etc.) — quem já está logado tem o idioma controlado pelo
    seletor de Configurações (`User.language`, salvo no banco); aqui é só
    um cookie de longa duração, pra visitante sem conta ainda escolher
    português/inglês/espanhol no dropdown de bandeiras.
    """
    from app.utils.i18n import IDIOMAS_SUPORTADOS

    if codigo not in IDIOMAS_SUPORTADOS:
        codigo = "pt-br"

    destino = request.referrer or url_for("main.index")
    resposta = redirect(destino)
    resposta.set_cookie(
        "nomdo_lang",
        codigo,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
    )
    return resposta


@main_bp.route("/configuracoes")
@login_required
def configuracoes():
    user = db.session.get(User, session["user_id"])
    return render_template("configuracoes.html", **_ctx(user))


@main_bp.route("/configuracoes/salvar", methods=["POST"])
@login_required
def salvar_configuracoes():
    user = db.session.get(User, session["user_id"])

    theme = (request.form.get("theme") or "light").strip()
    language = (request.form.get("language") or "pt-br").strip()
    currency = (request.form.get("currency") or "BRL").strip()

    if theme not in {"light", "dark", "auto"}:
        theme = "light"
    if language not in {"pt-br", "en", "es"}:
        language = "pt-br"
    if currency not in {"BRL", "USD", "EUR"}:
        currency = "BRL"

    user.theme = theme
    user.language = language
    user.currency = currency
    user.notify_browser = request.form.get("notify_browser") == "1"
    user.notify_email = request.form.get("notify_email") == "1"

    db.session.commit()

    flash("Configurações salvas com sucesso!", "sucesso")
    return redirect(url_for("main.configuracoes"))


@main_bp.route("/financas")
@login_required
def financas():
    user = db.session.get(User, session["user_id"])
    owner_id = user.owner_id

    lista_imoveis = Imovel.query.filter_by(
        user_id=owner_id
    ).all()

    imovel_titulos = {i.id: i.titulo for i in lista_imoveis}
    imovel_ids     = [i.id for i in lista_imoveis]

    dados_financeiros = []

    # =====================================================
    # LANÇAMENTOS MANUAIS (Financeiro)
    # -----------------------------------------------------
    # Continuam existindo para receitas fora do fluxo de Estadias
    # (ex.: aluguel combinado por fora, sem passar pela tela Imóveis).
    # =====================================================
    registros = Financeiro.query.filter_by(
        user_id=owner_id
    ).order_by(Financeiro.id.desc()).all()

    for r in registros:
        # CORREÇÃO CRÍTICA: Validação inline para evitar NoneType.strftime() se a data for NULL
        dados_financeiros.append({
            "id": r.id,
            "tipo": "manual",
            "editavel": True,
            "imovel": r.imovel,
            "status": r.status,
            "site": r.site,
            "descricao": r.descricao or "",
            "entrada": r.entrada.strftime("%Y-%m-%d") if r.entrada else "",
            "saida": r.saida.strftime("%Y-%m-%d") if r.saida else "",
            "bruto": float(r.bruto or 0),
            "liqPlat": float(r.liq_plat or 0),
            "data": r.data_registro.strftime("%Y-%m-%d") if r.data_registro else "",
            "despesas": [
                # CORREÇÃO: a chave era "name" aqui mas o front-end (editarRegistro)
                # sempre leu "nome" — os nomes das despesas ficavam em branco ao
                # reabrir um registro pra edição.
                {
                    "nome": d.nome,
                    "valor": float(d.valor or 0)
                }
                for d in r.despesas
            ]
        })

    # =====================================================
    # ESTADIAS (Imóveis + Estadia)
    # -----------------------------------------------------
    # Toda estadia real (feita na tela Imóveis) entra automaticamente
    # como um lançamento de receita aqui, já com os itens/cobranças
    # cadastrados por lá. Canceladas e bloqueios não são receita, então
    # não entram no balanço financeiro.
    # =====================================================
    estadias = []
    if imovel_ids:
        estadias = (
            Estadia.query
            .filter(Estadia.imovel_id.in_(imovel_ids))
            .filter(Estadia.status.notin_(["cancelada", "bloqueio"]))
            .order_by(Estadia.data_checkin.desc())
            .all()
        )

    for e in estadias:
        dados_financeiros.append({
            "id": e.id,
            "tipo": "estadia",
            "editavel": False,  # editar/excluir só na tela Imóveis > Estadias
            "imovel": imovel_titulos.get(e.imovel_id, ""),
            "hospede": e.nome_hospede or "",
            "status": e.status,
            "site": e.canal,
            "entrada": e.data_checkin.isoformat()  if e.data_checkin  else "",
            "saida":   e.data_checkout.isoformat() if e.data_checkout else "",
            "bruto":   float(e.valor_bruto or 0),
            "liqPlat": float(e.valor_liquido or 0),
            "data": e.criado_em.strftime("%Y-%m-%d") if e.criado_em else "",
            "despesas": [
                {"nome": i.descricao, "valor": float(i.valor or 0)}
                for i in e.itens
            ]
        })

    # =====================================================
    # DESPESAS GERAIS (não ligadas a nenhuma estadia)
    # -----------------------------------------------------
    # IPTU, condomínio, manutenção, seguro etc. Entram na MESMA tabela de
    # lançamentos (marcadas como "Despesa Geral"), pra não precisar de uma
    # seção/tabela separada só pra isso — o balanço já é único de qualquer
    # forma, então a listagem também passa a ser.
    # =====================================================
    despesas_gerais_objs = DespesaGeral.query.filter_by(
        user_id=owner_id
    ).order_by(DespesaGeral.data.desc()).all()

    for d in despesas_gerais_objs:
        dados_financeiros.append(
            _despesa_geral_para_lancamento(d, imovel_titulos.get(d.imovel_id, ""))
        )

    # Lançamentos mais recentes primeiro, misturando manuais, estadias e despesas gerais
    dados_financeiros.sort(key=lambda d: d.get("entrada") or d.get("data") or "", reverse=True)

    return render_template(
        "financas.html",
        imoveis=lista_imoveis,
        dados_financeiros=dados_financeiros,
        **_ctx(user)
    )


@main_bp.route("/api/financas/salvar", methods=["POST"])
@login_required
def salvar_financas():

    try:
        data = request.get_json()
        owner_id = get_effective_owner_id()
        financeiro_id = data.get("id")

        if financeiro_id:
            financeiro = Financeiro.query.filter_by(
                id=financeiro_id,
                user_id=owner_id
            ).first()

            if not financeiro:
                return jsonify({
                    "success": False,
                    "message": "Registro não encontrado"
                }), 404
        else:
            financeiro = Financeiro(
                user_id=owner_id
            )
            db.session.add(financeiro)

        # =========================
        # CONVERTER DATAS
        # =========================
        entrada = None
        saida = None

        if data.get("entrada"):
            entrada = datetime.strptime(
                data.get("entrada"),
                "%Y-%m-%d"
            ).date()

        if data.get("saida"):
            saida = datetime.strptime(
                data.get("saida"),
                "%Y-%m-%d"
            ).date()

        # =========================
        # CAMPOS
        # =========================
        financeiro.imovel = data.get("imovel")
        financeiro.site = data.get("site")
        financeiro.status = data.get("status")

        financeiro.bruto = float(data.get("bruto", 0))
        financeiro.liq_plat = float(data.get("liqPlat", 0))

        financeiro.entrada = entrada
        financeiro.saida = saida

        # =========================
        # FLUSH PRIMEIRO
        # =========================
        db.session.flush()

        # =========================
        # REMOVE DESPESAS ANTIGAS
        # =========================
        FinanceiroDespesa.query.filter_by(
            financeiro_id=financeiro.id
        ).delete()

        # =========================
        # NOVAS DESPESAS
        # =========================
        for despesa in data.get("despesas", []):
            nova = FinanceiroDespesa(
                financeiro_id=financeiro.id,
                nome=despesa.get("nome"),
                valor=float(despesa.get("valor", 0))
            )
            db.session.add(nova)

        db.session.commit()

        # CORREÇÃO CRÍTICA: Validação inline também no retorno JSON de criação da API
        return jsonify({
            "success": True,
            "registro": {
                "id": financeiro.id,
                "tipo": "manual",
                "editavel": True,
                "data": financeiro.data_registro.strftime("%Y-%m-%d") if financeiro.data_registro else "",
                "imovel": financeiro.imovel,
                "site": financeiro.site,
                "status": financeiro.status,
                "bruto": float(financeiro.bruto),
                "liqPlat": float(financeiro.liq_plat),
                "entrada": financeiro.entrada.strftime("%Y-%m-%d") if financeiro.entrada else "",
                "saida": financeiro.saida.strftime("%Y-%m-%d") if financeiro.saida else "",
                "despesas": [
                    {
                        "nome": d.nome,
                        "valor": float(d.valor)
                    }
                    for d in financeiro.despesas
                ]
            }
        })

    except Exception as e:
        traceback.print_exc()
        db.session.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@main_bp.route("/api/financas/excluir/<int:id>", methods=["DELETE"])
@login_required
def excluir_financas(id):
    owner_id = get_effective_owner_id()

    financeiro = Financeiro.query.filter_by(
        id=id,
        user_id=owner_id
    ).first()

    if not financeiro:
        return jsonify({
            "success": False,
            "message": "Registro não encontrado"
        }), 404

    # remove despesas primeiro
    FinanceiroDespesa.query.filter_by(
        financeiro_id=financeiro.id
    ).delete()

    db.session.delete(financeiro)
    db.session.commit()

    return jsonify({
        "success": True
    })


@main_bp.route("/api/financas/lancamento/salvar", methods=["POST"])
@login_required
def salvar_lancamento_financeiro():
    """
    Lançamento manual unificado: substitui as antigas telas separadas de
    "Novo Registro" e "Nova Despesa Geral" por um único formulário com
    Imóvel, Valor (com sinal), Data e Descrição — valor positivo entra
    como receita (Faturamento Bruto), valor negativo entra como despesa
    (Total Despesas), sem precisar detalhar site/canal nem taxa de
    plataforma pra um lançamento manual.

    Se o registro editado era uma DespesaGeral antiga (tipo "despesa_geral"),
    ela é migrada pra esta mesma tabela unificada (Financeiro) — a partir
    da primeira edição, o lançamento passa a viver só aqui.
    """
    try:
        data = request.get_json() or {}
        owner_id = get_effective_owner_id()

        imovel_titulo = (data.get("imovel") or "").strip()
        if not imovel_titulo:
            return jsonify({
                "success": False,
                "message": "Selecione um imóvel."
            }), 400

        try:
            valor = float(data.get("valor", 0) or 0)
        except (TypeError, ValueError):
            valor = 0.0

        if valor == 0:
            return jsonify({
                "success": False,
                "message": "Informe um valor diferente de zero."
            }), 400

        descricao = (data.get("descricao") or "").strip()

        data_lanc = None
        if data.get("data"):
            data_lanc = datetime.strptime(data.get("data"), "%Y-%m-%d").date()

        lanc_id = data.get("id")
        tipo_original = data.get("tipo") or "manual"

        substituiu = None

        # Editando uma Despesa Geral antiga: remove o registro legado e
        # migra pra um Financeiro novo — não fica com os dois duplicados.
        if tipo_original == "despesa_geral" and lanc_id:
            antiga = DespesaGeral.query.filter_by(id=lanc_id, user_id=owner_id).first()
            if antiga:
                substituiu = {"id": antiga.id, "tipo": "despesa_geral"}
                db.session.delete(antiga)
                db.session.flush()
            lanc_id = None

        if lanc_id:
            financeiro = Financeiro.query.filter_by(id=lanc_id, user_id=owner_id).first()
            if not financeiro:
                return jsonify({
                    "success": False,
                    "message": "Registro não encontrado"
                }), 404
        else:
            financeiro = Financeiro(user_id=owner_id)
            db.session.add(financeiro)

        financeiro.imovel = imovel_titulo
        financeiro.site = None
        financeiro.status = None
        financeiro.descricao = descricao or None
        financeiro.entrada = data_lanc
        financeiro.saida = None

        if valor >= 0:
            financeiro.bruto = valor
            financeiro.liq_plat = valor
        else:
            financeiro.bruto = 0.0
            financeiro.liq_plat = 0.0

        db.session.flush()

        # Remove despesas antigas do registro (se veio de uma edição) e
        # recria a partir do sinal do valor atual.
        FinanceiroDespesa.query.filter_by(
            financeiro_id=financeiro.id
        ).delete()

        if valor < 0:
            db.session.add(FinanceiroDespesa(
                financeiro_id=financeiro.id,
                nome=descricao or "Despesa",
                valor=abs(valor)
            ))

        db.session.commit()

        return jsonify({
            "success": True,
            "substituiu": substituiu,
            "registro": {
                "id": financeiro.id,
                "tipo": "manual",
                "editavel": True,
                "imovel": financeiro.imovel,
                "status": None,
                "site": None,
                "descricao": financeiro.descricao or "",
                "entrada": financeiro.entrada.strftime("%Y-%m-%d") if financeiro.entrada else "",
                "saida": "",
                "bruto": float(financeiro.bruto or 0),
                "liqPlat": float(financeiro.liq_plat or 0),
                "data": financeiro.entrada.strftime("%Y-%m-%d") if financeiro.entrada else "",
                "despesas": [
                    {"nome": d.nome, "valor": float(d.valor)}
                    for d in financeiro.despesas
                ],
            }
        })

    except Exception as e:
        traceback.print_exc()
        db.session.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# DESPESAS GERAIS (custos do imóvel sem estadia associada)
# =========================================================

@main_bp.route("/api/despesas-gerais/salvar", methods=["POST"])
@login_required
def salvar_despesa_geral():
    try:
        data = request.get_json()
        owner_id = get_effective_owner_id()

        # imovel_id vem do <select> do front-end como string — converte
        # explicitamente pra não depender de coerção implícita do driver
        # do banco (Postgres não aceita comparar texto com coluna inteira).
        try:
            imovel_id = int(data.get("imovel_id"))
        except (TypeError, ValueError):
            imovel_id = None

        imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first() if imovel_id else None

        if not imovel:
            return jsonify({
                "success": False,
                "message": "Selecione um imóvel válido."
            }), 400

        categoria = (data.get("categoria") or "").strip()
        # A categoria já É a descrição da despesa (IPTU, Condomínio...) —
        # "nome" só existe de fato quando a categoria escolhida é "Outro".
        # Sem categoria selecionada, não há o que salvar.
        nome = (data.get("nome") or "").strip() or categoria
        if not categoria:
            return jsonify({
                "success": False,
                "message": "Selecione o que é essa despesa."
            }), 400
        if not nome:
            return jsonify({
                "success": False,
                "message": "Especifique a despesa."
            }), 400

        despesa_id = data.get("id")

        if despesa_id:
            despesa = DespesaGeral.query.filter_by(
                id=despesa_id,
                user_id=owner_id
            ).first()

            if not despesa:
                return jsonify({
                    "success": False,
                    "message": "Despesa não encontrada"
                }), 404
        else:
            despesa = DespesaGeral(user_id=owner_id)
            db.session.add(despesa)

        data_despesa = None
        if data.get("data"):
            data_despesa = datetime.strptime(data.get("data"), "%Y-%m-%d").date()

        despesa.imovel_id   = imovel.id
        despesa.nome        = nome
        despesa.categoria   = categoria or None
        despesa.valor       = float(data.get("valor", 0) or 0)
        despesa.data        = data_despesa or despesa.data or datetime.utcnow().date()
        despesa.observacoes = (data.get("observacoes") or "").strip() or None

        db.session.commit()

        return jsonify({
            "success": True,
            # Mesmo formato dos outros lançamentos (bruto/liqPlat/despesas[]),
            # pra entrar direto na tabela única de Finanças no front-end.
            "registro": _despesa_geral_para_lancamento(despesa, imovel.titulo)
        })

    except Exception as e:
        traceback.print_exc()
        db.session.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@main_bp.route("/api/despesas-gerais/excluir/<int:id>", methods=["DELETE"])
@login_required
def excluir_despesa_geral(id):
    owner_id = get_effective_owner_id()

    despesa = DespesaGeral.query.filter_by(
        id=id,
        user_id=owner_id
    ).first()

    if not despesa:
        return jsonify({
            "success": False,
            "message": "Despesa não encontrada"
        }), 404

    try:
        db.session.delete(despesa)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@main_bp.route("/hub-anfitriao")
@login_required
def hub_anfitriao():
    """
    Central Operacional Inteligente — página minimalista que só responde
    "o que precisa da minha atenção agora?". Todo o conteúdo (prioridades,
    resumo, imóveis em atenção, insights) é buscado no cliente via
    GET /api/hub/dados (ver app/routes/hub.py); esta rota não precisa
    passar nenhum contexto pro template além do que já vem globalmente
    (nome_completo, current_lang etc. via context_processor).

    O único trabalho feito aqui é o efeito colateral de processar
    rotinas/lembretes vencidos (pilha, limpeza pós-checkout, custom) e
    disparar tarefa + e-mail pro anfitrião antes de renderizar a página —
    o mesmo processamento que /api/hub/dados também dispara, então rodar
    aqui de novo é redundante mas inofensivo (idempotente) e garante que
    a pílula de status já reflita lembretes recém-vencidos assim que a
    página carrega.
    """
    owner_id = get_effective_owner_id()

    try:
        from app.routes.hub import processar_lembretes
        # Os imóveis pertencem à conta Proprietária — se quem está logado é
        # um Anfitrião-ajudante, processa em nome do Proprietário (owner_id).
        user_atual = db.session.get(User, owner_id)
        if user_atual:
            processar_lembretes(user_atual)
    except Exception:
        current_app.logger.exception("Falha ao processar lembretes do Hub")

    # ── Abas (Limpezas/Manutenções/Checklists/Rotinas/Precificação) ────────
    # O produto virou uma única página com abas em vez de páginas separadas;
    # cada aba continua com sua própria função de contexto (em pg_*.py),
    # chamada aqui só uma vez por request. Só a aba ATIVA recebe os filtros
    # da query string (`?imovel_id=`/`status=`/`tipo=` etc.) — as outras 4
    # abas, mesmo sendo renderizadas no mesmo request (todas ficam no DOM,
    # só uma visível via CSS), usam um MultiDict vazio, senão um filtro
    # digitado numa aba "vazaria" pras outras 4 que também leem `imovel_id`.
    from werkzeug.datastructures import MultiDict
    from app.routes.pg_tarefas import contexto_tarefas
    from app.routes.pg_checklists import contexto_checklists
    from app.routes.pg_rotinas import contexto_rotinas
    from app.routes.pg_precificacao import contexto_precificacao

    ABAS_VALIDAS = {"hoje", "tarefas", "checklists", "rotinas", "precificacao"}
    tab_ativa = request.args.get("tab", "hoje")
    if tab_ativa not in ABAS_VALIDAS:
        tab_ativa = "hoje"

    args_vazios = MultiDict()

    ctx_tarefas = contexto_tarefas(
        owner_id, request.args if tab_ativa == "tarefas" else args_vazios
    )
    ctx_checklists = contexto_checklists(
        owner_id, request.args if tab_ativa == "checklists" else args_vazios
    )
    ctx_rotinas = contexto_rotinas(
        owner_id, request.args if tab_ativa == "rotinas" else args_vazios
    )
    ctx_precificacao = contexto_precificacao(
        owner_id, request.args if tab_ativa == "precificacao" else args_vazios
    )

    return render_template(
        "hub_anfitriao.html",
        tab_ativa=tab_ativa,
        # Cuidados do Imóvel (aba unificada)
        tarefas_pendentes=ctx_tarefas["tarefas_pendentes"],
        tarefas_concluidas=ctx_tarefas["tarefas_concluidas"],
        tarefas_imoveis=ctx_tarefas["imoveis"],
        tarefas_filtro_imovel_id=ctx_tarefas["filtro_imovel_id"],
        tarefas_filtro_tipo=ctx_tarefas["filtro_tipo"],
        tarefas_tipos_lembrete=ctx_tarefas["tipos_lembrete"],
        # Checklists
        checklists_imoveis=ctx_checklists["imoveis"],
        checklists_imovel_selecionado=ctx_checklists["imovel_selecionado"],
        checklists_modelo_antes=ctx_checklists["modelo_antes"],
        checklists_modelo_depois=ctx_checklists["modelo_depois"],
        checklists_estadia_atual=ctx_checklists["estadia_atual"],
        # Rotinas
        rotinas_rotinas=ctx_rotinas["rotinas"],
        rotinas_imoveis=ctx_rotinas["imoveis"],
        rotinas_tipos_lembrete=ctx_rotinas["tipos_lembrete"],
        rotinas_tipos_evento=ctx_rotinas["tipos_evento"],
        rotinas_filtro_imovel_id=ctx_rotinas["filtro_imovel_id"],
        rotinas_filtro_tipo=ctx_rotinas["filtro_tipo"],
        # Precificação
        precificacao_pct=ctx_precificacao["pct_precificacao"],
        precificacao_imoveis=ctx_precificacao["imoveis"],
        precificacao_eventos=ctx_precificacao["eventos"],
        precificacao_oportunidades=ctx_precificacao["oportunidades"],
        precificacao_niveis_impacto=ctx_precificacao["niveis_impacto"],
    )


# =========================================================
# DASHBOARD FINANCEIRO DO PROPRIETÁRIO
# -----------------------------------------------------
# Exclusivo de quem é dono da conta (Proprietário) — um Anfitrião-ajudante
# opera os imóveis/estadias/hub do Proprietário, mas não vê o lucro real
# nem os custos fixos configurados aqui (decisão tomada na fase da
# hierarquia Proprietário/Anfitrião).
# =========================================================

@main_bp.route("/proprietario/dashboard")
@login_required
def dashboard_proprietario():
    user = db.session.get(User, session["user_id"])

    if user.e_ajudante:
        from app.utils.i18n import t_flash
        flash(
            t_flash(
                "O dashboard financeiro é exclusivo da conta Proprietária — "
                "fale com quem te convidou para ver esses dados."
            ),
            "erro",
        )
        return redirect(url_for("reservas.dashboard"))

    imoveis = Imovel.query.filter_by(user_id=user.id).all()

    hoje = datetime.utcnow()

    # Período sendo visualizado — vem da URL (?periodo=mes|trimestre|semestre|ano
    # &valor=...), caindo no período atual se não vier ou vier inválido. Isso
    # permite navegar entre meses/trimestres/semestres/anos (o faturamento/
    # despesas sempre mudam, então fixar só no período atual não servia pra
    # olhar períodos passados).
    periodo = request.args.get("periodo", "mes")
    if periodo not in MESES_POR_UNIDADE:
        periodo = "mes"

    ano_atual, unidade_atual = _periodo_atual(periodo, hoje)
    valor_param = request.args.get("valor", "") or request.args.get("mes", "")
    ano_ref, unidade_ref = _parse_valor_periodo(periodo, valor_param, hoje)

    primeiro_dia_mes, ultimo_dia_mes = _intervalo_periodo(periodo, ano_ref, unidade_ref)
    valor_anterior, valor_seguinte = _navegacao_periodo(periodo, ano_ref, unidade_ref)
    valor_atual = _formatar_valor_periodo(periodo, ano_ref, unidade_ref)
    eh_periodo_atual = (ano_ref == ano_atual and unidade_ref == unidade_atual)
    rotulo_periodo = ROTULO_PERIODO[periodo]

    dados_imoveis = []
    consolidado = {
        "faturamento_mes": 0.0,
        "despesas_mes": 0.0,
        "lucro_mes": 0.0,
        "faturamento_total": 0.0,
        "despesas_total": 0.0,
        "lucro_total": 0.0,
    }

    total_estadias_contabilizadas = 0

    for im in imoveis:
        estadias_im = (
            Estadia.query
            .filter(
                Estadia.imovel_id == im.id,
                Estadia.status.notin_(["cancelada", "bloqueio"]),
            )
            .all()
        )
        total_estadias_contabilizadas += len(estadias_im)

        faturamento_total = sum(float(e.valor_liquido or 0) for e in estadias_im)
        faturamento_mes = sum(
            float(e.valor_liquido or 0)
            for e in estadias_im
            if e.data_checkin and primeiro_dia_mes <= e.data_checkin <= ultimo_dia_mes
        )

        # Despesas (incluindo custos recorrentes tipo manutenção/contas, que
        # agora entram como um lançamento normal de Despesa Geral em vez de
        # um valor fixo configurado à parte) já são dinâmicas: somam tudo
        # que foi de fato lançado no mês corrente, então o lucro reflete
        # exatamente o que foi gasto, sem precisar reconfigurar nada todo mês.
        despesas_im = DespesaGeral.query.filter_by(imovel_id=im.id).all()
        despesas_total = sum(float(d.valor or 0) for d in despesas_im)
        despesas_mes = sum(
            float(d.valor or 0)
            for d in despesas_im
            if d.data and primeiro_dia_mes <= d.data <= ultimo_dia_mes
        )

        lucro_mes = faturamento_mes - despesas_mes
        lucro_total = faturamento_total - despesas_total

        dados_imoveis.append({
            "id": im.id,
            "titulo": im.titulo,
            "foto_principal": im.foto_principal,
            "faturamento_mes": faturamento_mes,
            "despesas_mes": despesas_mes,
            "lucro_mes": lucro_mes,
            "faturamento_total": faturamento_total,
            "despesas_total": despesas_total,
            "lucro_total": lucro_total,
        })

        consolidado["faturamento_mes"] += faturamento_mes
        consolidado["despesas_mes"] += despesas_mes
        consolidado["lucro_mes"] += lucro_mes
        consolidado["faturamento_total"] += faturamento_total
        consolidado["despesas_total"] += despesas_total
        consolidado["lucro_total"] += lucro_total

    dados_imoveis.sort(key=lambda x: x["lucro_mes"], reverse=True)

    return render_template(
        "proprietario_dashboard.html",
        imoveis=dados_imoveis,
        consolidado=consolidado,
        periodo=periodo,
        mes_referencia=_label_periodo(periodo, ano_ref, unidade_ref),
        mes_valor=valor_atual,
        mes_anterior=valor_anterior,
        mes_seguinte=valor_seguinte,
        eh_mes_atual=eh_periodo_atual,
        rotulo_periodo=rotulo_periodo,
        tem_imoveis=bool(imoveis),
        tem_estadias=total_estadias_contabilizadas > 0,
        **_ctx(user)
    )