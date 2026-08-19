"""
app/routes/api.py
Blueprint JSON aditivo, usado exclusivamente pelo app mobile (Expo).

Não altera nem remove nenhuma rota HTML existente — é uma camada extra
que expõe, em JSON, as mesmas informações que o site já mostra.

Autenticação: em vez da sessão de cookie usada pelo site, aqui usamos um
token assinado (itsdangerous), enviado pelo app como:
    Authorization: Bearer <token>
Isso evita depender de cookies (que não fazem sentido num app nativo) e
mantém esta camada isolada da sessão Flask do site.
"""

import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal
from functools import wraps

from flask import Blueprint, request, jsonify, current_app, g, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func as sa_func

from app.extensions import db, csrf
from app.models import User, Imovel, Estadia, Grupo, HubTarefa, ConviteAnfitriao
from app.models.financas import Financeiro, FinanceiroDespesa, DespesaGeral
from app.models.hub import TIPOS_LEMBRETE
from app.routes.hub import processar_lembretes, DIAS_PILHA_PADRAO
from app.utils import formatar_nome_exibicao
from app.services.email_service import enviar_email_convite_anfitriao
from app.services import enviar_email_despedida

api_bp = Blueprint("api", __name__, url_prefix="/api")

# O app mobile não usa cookies/sessão -> não faz sentido exigir CSRF aqui
# (CSRF protege contra requisições forjadas via navegador autenticado por
# cookie; um cliente nativo com Bearer token não está exposto a isso).
csrf.exempt(api_bp)

TOKEN_SALT = "api-mobile"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias, mesmo prazo da sessão "lembrar-me" do site


# ============================================================
# TOKEN HELPERS
# ============================================================

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=TOKEN_SALT)


def gerar_token(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def _decodificar_token(token: str):
    try:
        dados = _serializer().loads(token, max_age=TOKEN_MAX_AGE)
        return dados.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


def api_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"erro": "Token ausente."}), 401

        token = auth_header[len("Bearer "):].strip()
        user_id = _decodificar_token(token)
        if not user_id:
            return jsonify({"erro": "Token inválido ou expirado."}), 401

        user = db.session.get(User, user_id)
        if not user or not user.is_active:
            return jsonify({"erro": "Usuário não encontrado ou inativo."}), 401

        g.current_user = user
        return func(*args, **kwargs)

    return wrapper


ADMIN_EMAILS = ("grouppietra@gmail.com", "giovanna.perovano@clona.com.br")  # mesma constante de app/routes/admin.py


def api_admin_required(func):
    @wraps(func)
    @api_login_required
    def wrapper(*args, **kwargs):
        user = g.current_user
        if user.is_admin or user.email.lower() in ADMIN_EMAILS:
            return func(*args, **kwargs)
        return jsonify({"erro": "Acesso restrito ao Painel Master."}), 403

    return wrapper


def _user_publico(user: User) -> dict:
    return {
        "id": user.id,
        "nome": user.nome,
        "email": user.email,
        "categoria": user.categoria,
        "papel": user.papel,
        "is_admin": bool(user.is_admin),
        "e_ajudante": user.e_ajudante,
        "foto": _url_foto_usuario(user.foto),
        "theme": user.theme,
    }


# ============================================================
# AUTH
# ============================================================

@api_bp.route("/auth/login", methods=["POST"])
def login():
    dados = request.get_json(silent=True) or {}
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""

    if not email or not senha:
        return jsonify({"erro": "Informe e-mail e senha."}), 400

    user = User.query.filter_by(email=email).first()

    if not user or user.auth_provider != "email" or not user.verificar_senha(senha):
        if not user:
            return jsonify({"erro": "Esse e-mail não está cadastrado."}), 401
        if user.auth_provider != "email":
            return jsonify({"erro": "Essa conta usa login do Google. Use o app com sua conta Google."}), 401
        return jsonify({"erro": "E-mail ou senha incorretos."}), 401

    if not user.is_confirmed:
        return jsonify({"erro": "Confirme seu e-mail antes de entrar."}), 401

    if not user.is_active:
        return jsonify({"erro": "Sua conta está desativada."}), 401

    user.last_login_at = datetime.utcnow()
    db.session.commit()

    token = gerar_token(user.id)
    return jsonify({"token": token, "user": _user_publico(user)})


@api_bp.route("/auth/me", methods=["GET"])
@api_login_required
def me():
    return jsonify({"user": _user_publico(g.current_user)})


# ============================================================
# DASHBOARD
# (mesma lógica de app/routes/reservas.py::dashboard, só que devolvendo
#  JSON em vez de renderizar dashboard.html — sem alterar o arquivo original)
# ============================================================

def _formatar_moeda(valor) -> str:
    return "{:,.2f}".format(valor).replace(",", "X").replace(".", ",").replace("X", ".")


@api_bp.route("/dashboard", methods=["GET"])
@api_login_required
def dashboard():
    user = g.current_user
    hoje = date.today()

    imoveis = Imovel.query.filter_by(user_id=user.id).all()
    imovel_ids = [i.id for i in imoveis]
    imovel_titulos = {i.id: i.titulo for i in imoveis}

    estadias_host = (
        Estadia.query.filter(Estadia.imovel_id.in_(imovel_ids)).all()
        if imovel_ids else []
    )

    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    primeiro_dia_mes = hoje.replace(day=1)
    ultimo_dia_mes = hoje.replace(day=dias_no_mes)

    reservas_ativas_host = 0
    checkins_hoje = 0
    faturamento_total = Decimal("0.00")
    faturamento_mes = Decimal("0.00")
    dias_ocupados_mes = 0
    estadias_por_imovel = {}
    faturamento_por_imovel = {}

    for e in estadias_host:
        if e.status == "cancelada":
            continue

        if e.status != "bloqueio":
            if e.data_checkin and e.data_checkout and e.data_checkin <= hoje <= e.data_checkout:
                reservas_ativas_host += 1
            if e.data_checkin == hoje:
                checkins_hoje += 1

            valor_estadia = Decimal(str(e.valor_bruto or 0))
            faturamento_total += valor_estadia
            estadias_por_imovel[e.imovel_id] = estadias_por_imovel.get(e.imovel_id, 0) + 1
            faturamento_por_imovel[e.imovel_id] = faturamento_por_imovel.get(e.imovel_id, Decimal("0.00")) + valor_estadia

        if (e.data_checkin and e.data_checkout
                and e.data_checkin <= ultimo_dia_mes and e.data_checkout >= primeiro_dia_mes):
            inicio_ef = max(e.data_checkin, primeiro_dia_mes)
            fim_ef = min(e.data_checkout, ultimo_dia_mes)
            dias_ocupados_mes += max(0, (fim_ef - inicio_ef).days)
            if e.status != "bloqueio":
                faturamento_mes += Decimal(str(e.valor_bruto or 0))

    total_imoveis = len(imoveis)
    tem_estadias = bool(estadias_host)
    dashboard_desbloqueado = total_imoveis > 0 and tem_estadias

    media_ocupacao = 0.0
    if total_imoveis and dias_no_mes:
        media_ocupacao = round(min(100, (dias_ocupados_mes / (dias_no_mes * total_imoveis)) * 100), 1)

    revpar = (faturamento_mes / total_imoveis) if total_imoveis else Decimal("0.00")

    contagem_todos_imoveis = {i.id: estadias_por_imovel.get(i.id, 0) for i in imoveis}
    imovel_mais_procurado = ""
    imovel_menos_procurado = ""
    if contagem_todos_imoveis and any(qtd > 0 for qtd in contagem_todos_imoveis.values()):
        mais_id = max(contagem_todos_imoveis, key=contagem_todos_imoveis.get)
        imovel_mais_procurado = imovel_titulos.get(mais_id, "")
        if len(contagem_todos_imoveis) > 1:
            menos_id = min(contagem_todos_imoveis, key=contagem_todos_imoveis.get)
            imovel_menos_procurado = imovel_titulos.get(menos_id, "")

    stats = {
        "total_imoveis": total_imoveis,
        "reservas_ativas": reservas_ativas_host,
        "checkins_hoje": checkins_hoje,
        "faturamento_total": _formatar_moeda(faturamento_total),
        "media_ocupacao": media_ocupacao,
        "imovel_mais_procurado": imovel_mais_procurado,
        "imovel_menos_procurado": imovel_menos_procurado,
        "revpar": _formatar_moeda(revpar),
    }

    faturamento_chart_labels = [i.titulo for i in imoveis]
    faturamento_chart_values = [
        float(faturamento_por_imovel.get(i.id, Decimal("0.00"))) for i in imoveis
    ]
    estadias_chart_values = [estadias_por_imovel.get(i.id, 0) for i in imoveis]

    return jsonify({
        "tem_imoveis": total_imoveis > 0,
        "tem_estadias": tem_estadias,
        "dashboard_desbloqueado": dashboard_desbloqueado,
        "stats": stats,
        "faturamento_chart": {
            "labels": faturamento_chart_labels,
            "values": faturamento_chart_values,
        },
        "estadias_chart": {
            "labels": faturamento_chart_labels,
            "values": estadias_chart_values,
        },
    })


# ============================================================
# IMÓVEIS
# (mesma lógica/validações de app/routes/imoveis.py, devolvendo JSON.
#  Upload de foto não entra nesta primeira versão do app.)
# ============================================================

def _url_foto(nome_arquivo):
    if not nome_arquivo:
        return None
    return f"{request.host_url.rstrip('/')}/static/uploads/{nome_arquivo}"


def _url_foto_usuario(caminho):
    """
    User.foto já é salvo com o prefixo 'uploads/' embutido (diferente de
    Imovel.foto_principal, que salva só o nome do arquivo) — por isso tem
    um helper próprio, pra não duplicar 'uploads/uploads/...' na URL.
    """
    if not caminho:
        return None
    return f"{request.host_url.rstrip('/')}/static/{caminho}"


def _imovel_publico(imovel: Imovel) -> dict:
    return {
        "id": imovel.id,
        "titulo": imovel.titulo,
        "endereco": imovel.endereco,
        "ponto_referencia": imovel.ponto_referencia,
        "grupo_id": imovel.grupo_id,
        "pattern": (imovel.id * 3 + 1) % 8,
        "foto_principal": _url_foto(imovel.foto_principal),
        "cidade": imovel.cidade,
        "estado": imovel.estado,
        "wifi_rede": imovel.wifi_rede,
        "wifi_senha": imovel.wifi_senha,
        "senha_fechadura": imovel.senha_fechadura,
        "contato_telefone": imovel.contato_telefone,
        "contato_email": imovel.contato_email,
        "checkin_padrao": imovel.checkin_padrao,
        "checkout_padrao": imovel.checkout_padrao,
        "diaria_base": float(imovel.diaria_base) if imovel.diaria_base is not None else None,
        "taxa_limpeza_padrao": float(imovel.taxa_limpeza_padrao) if imovel.taxa_limpeza_padrao is not None else None,
        "capacidade_max": imovel.capacidade_max,
        "qtd_quartos": imovel.qtd_quartos,
        "qtd_banheiros": imovel.qtd_banheiros,
        "qtd_camas": imovel.qtd_camas,
        "slug_publico": imovel.slug_publico,
    }


_CAMPOS_IMOVEL_OPCIONAIS = (
    "wifi_rede", "wifi_senha", "senha_fechadura",
    "contato_telefone", "contato_email",
    "checkin_padrao", "checkout_padrao",
    "cidade", "estado",
)
_CAMPOS_IMOVEL_NUMERICOS = (
    "diaria_base", "taxa_limpeza_padrao",
    "capacidade_max", "qtd_quartos", "qtd_banheiros", "qtd_camas",
)
_CAMPOS_IMOVEL_INTEIROS = ("capacidade_max", "qtd_quartos", "qtd_banheiros", "qtd_camas")


def _aplicar_campos_imovel(imovel: Imovel, dados: dict) -> None:
    for campo in _CAMPOS_IMOVEL_OPCIONAIS:
        if campo in dados:
            valor = (dados.get(campo) or "").strip() if isinstance(dados.get(campo), str) else dados.get(campo)
            setattr(imovel, campo, valor or None)

    for campo in _CAMPOS_IMOVEL_NUMERICOS:
        if campo in dados:
            valor = dados.get(campo)
            if valor in (None, ""):
                setattr(imovel, campo, None)
            else:
                try:
                    setattr(imovel, campo, int(valor) if campo in _CAMPOS_IMOVEL_INTEIROS else float(valor))
                except (TypeError, ValueError):
                    pass

    if "ponto_referencia" in dados:
        imovel.ponto_referencia = (dados.get("ponto_referencia") or "").strip() or None
    if "grupo_id" in dados:
        imovel.grupo_id = dados.get("grupo_id") or None


@api_bp.route("/imoveis", methods=["GET"])
@api_login_required
def listar_imoveis():
    owner_id = g.current_user.owner_id
    imoveis = Imovel.query.filter_by(user_id=owner_id).all()
    return jsonify({"imoveis": [_imovel_publico(i) for i in imoveis]})


@api_bp.route("/imoveis/<int:imovel_id>", methods=["GET"])
@api_login_required
def detalhes_imovel(imovel_id: int):
    owner_id = g.current_user.owner_id
    imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first()
    if not imovel:
        return jsonify({"erro": "Imóvel não encontrado."}), 404
    return jsonify({"imovel": _imovel_publico(imovel)})


@api_bp.route("/imoveis", methods=["POST"])
@api_login_required
def criar_imovel():
    owner_id = g.current_user.owner_id
    dados = request.get_json(silent=True) or {}

    titulo = (dados.get("titulo") or "").strip()
    endereco = (dados.get("endereco") or "").strip()

    if not titulo:
        return jsonify({"erro": "Informe o título do imóvel."}), 400
    if not endereco:
        return jsonify({"erro": "Endereço é obrigatório."}), 400
    if Imovel.query.filter_by(user_id=owner_id, titulo=titulo).first():
        return jsonify({"erro": "Já existe um imóvel com esse nome."}), 400

    novo = Imovel(titulo=titulo, endereco=endereco, user_id=owner_id)
    _aplicar_campos_imovel(novo, dados)
    novo.gerar_slug()

    db.session.add(novo)
    db.session.commit()
    return jsonify({"imovel": _imovel_publico(novo)}), 201


@api_bp.route("/imoveis/<int:imovel_id>", methods=["PUT"])
@api_login_required
def editar_imovel(imovel_id: int):
    owner_id = g.current_user.owner_id
    imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first()
    if not imovel:
        return jsonify({"erro": "Imóvel não encontrado."}), 404

    dados = request.get_json(silent=True) or {}

    if "titulo" in dados:
        titulo = (dados.get("titulo") or "").strip()
        if not titulo:
            return jsonify({"erro": "O título não pode ficar vazio."}), 400
        if Imovel.query.filter(
            Imovel.id != imovel_id, Imovel.user_id == owner_id, Imovel.titulo == titulo
        ).first():
            return jsonify({"erro": "Já existe um imóvel com esse nome."}), 400
        if imovel.titulo != titulo:
            imovel.titulo = titulo
            imovel.gerar_slug()

    if "endereco" in dados:
        endereco = (dados.get("endereco") or "").strip()
        if not endereco:
            return jsonify({"erro": "Endereço é obrigatório."}), 400
        imovel.endereco = endereco

    _aplicar_campos_imovel(imovel, dados)

    db.session.commit()
    return jsonify({"imovel": _imovel_publico(imovel)})


@api_bp.route("/imoveis/<int:imovel_id>", methods=["DELETE"])
@api_login_required
def excluir_imovel(imovel_id: int):
    owner_id = g.current_user.owner_id
    imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first()
    if not imovel:
        return jsonify({"erro": "Imóvel não encontrado."}), 404

    try:
        db.session.delete(imovel)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "erro": str(exc)}), 500


# ============================================================
# GRUPOS
# ============================================================

def _grupo_publico(grupo: Grupo) -> dict:
    return {
        "id": grupo.id,
        "nome": grupo.nome,
        "imovel_ids": [i.id for i in grupo.imoveis],
        "imoveis_count": len(grupo.imoveis),
    }


@api_bp.route("/grupos", methods=["GET"])
@api_login_required
def listar_grupos():
    owner_id = g.current_user.owner_id
    grupos = Grupo.query.filter_by(user_id=owner_id).all()
    return jsonify({"grupos": [_grupo_publico(gr) for gr in grupos]})


@api_bp.route("/grupos", methods=["POST"])
@api_login_required
def criar_grupo():
    owner_id = g.current_user.owner_id
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    imovel_ids = dados.get("imovel_ids") or []

    if not nome:
        return jsonify({"erro": "Informe um nome pro grupo."}), 400

    grupo = Grupo(nome=nome, user_id=owner_id)
    db.session.add(grupo)
    db.session.flush()

    if imovel_ids:
        for imovel in Imovel.query.filter(
            Imovel.id.in_(imovel_ids), Imovel.user_id == owner_id
        ).all():
            imovel.grupo_id = grupo.id

    db.session.commit()
    return jsonify({"grupo": _grupo_publico(grupo)}), 201


@api_bp.route("/grupos/<int:grupo_id>", methods=["PUT"])
@api_login_required
def editar_grupo(grupo_id: int):
    owner_id = g.current_user.owner_id
    grupo = Grupo.query.filter_by(id=grupo_id, user_id=owner_id).first()
    if not grupo:
        return jsonify({"erro": "Grupo não encontrado."}), 404

    dados = request.get_json(silent=True) or {}

    if "nome" in dados:
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return jsonify({"erro": "O nome do grupo não pode ficar vazio."}), 400
        grupo.nome = nome

    if "imovel_ids" in dados:
        for imovel in grupo.imoveis:
            imovel.grupo_id = None
        imovel_ids = dados.get("imovel_ids") or []
        if imovel_ids:
            for imovel in Imovel.query.filter(
                Imovel.id.in_(imovel_ids), Imovel.user_id == owner_id
            ).all():
                imovel.grupo_id = grupo.id

    db.session.commit()
    return jsonify({"grupo": _grupo_publico(grupo)})


@api_bp.route("/grupos/<int:grupo_id>", methods=["DELETE"])
@api_login_required
def excluir_grupo(grupo_id: int):
    owner_id = g.current_user.owner_id
    grupo = Grupo.query.filter_by(id=grupo_id, user_id=owner_id).first()
    if not grupo:
        return jsonify({"erro": "Grupo não encontrado."}), 404

    try:
        for imovel in grupo.imoveis:
            imovel.grupo_id = None
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "erro": str(exc)}), 500


# ============================================================
# FINANÇAS
# (mesma lógica de app/routes/main.py — financas/salvar_financas/
#  excluir_financas/salvar_despesa_geral/excluir_despesa_geral —
#  devolvendo/recebendo JSON em vez de sessão + formulário HTML)
# ============================================================

def _despesa_geral_para_lancamento(despesa: DespesaGeral, imovel_titulo: str) -> dict:
    rotulo = despesa.categoria if (despesa.categoria and despesa.categoria != "Outro") else despesa.nome
    return {
        "id": despesa.id,
        "tipo": "despesa_geral",
        "editavel": True,
        "imovel_id": despesa.imovel_id,
        "imovel": imovel_titulo,
        "status": None,
        "site": None,
        "entrada": despesa.data.strftime("%Y-%m-%d") if despesa.data else "",
        "saida": "",
        "bruto": 0.0,
        "liqPlat": 0.0,
        "data": despesa.data.strftime("%Y-%m-%d") if despesa.data else "",
        "categoria": despesa.categoria or "",
        "observacoes": despesa.observacoes or "",
        "despesas": [{"nome": rotulo, "valor": float(despesa.valor or 0)}],
    }


@api_bp.route("/financas", methods=["GET"])
@api_login_required
def listar_financas():
    owner_id = g.current_user.owner_id

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).all()
    imovel_titulos = {i.id: i.titulo for i in lista_imoveis}
    imovel_ids = [i.id for i in lista_imoveis]

    lancamentos = []

    registros = Financeiro.query.filter_by(user_id=owner_id).order_by(Financeiro.id.desc()).all()
    for r in registros:
        lancamentos.append({
            "id": r.id,
            "tipo": "manual",
            "editavel": True,
            "imovel": r.imovel,
            "status": r.status,
            "site": r.site,
            "entrada": r.entrada.strftime("%Y-%m-%d") if r.entrada else "",
            "saida": r.saida.strftime("%Y-%m-%d") if r.saida else "",
            "bruto": float(r.bruto or 0),
            "liqPlat": float(r.liq_plat or 0),
            "data": r.data_registro.strftime("%Y-%m-%d") if r.data_registro else "",
            "despesas": [{"nome": d.nome, "valor": float(d.valor or 0)} for d in r.despesas],
        })

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
        lancamentos.append({
            "id": e.id,
            "tipo": "estadia",
            "editavel": False,
            "imovel": imovel_titulos.get(e.imovel_id, ""),
            "status": e.status,
            "site": e.canal,
            "entrada": e.data_checkin.isoformat() if e.data_checkin else "",
            "saida": e.data_checkout.isoformat() if e.data_checkout else "",
            "bruto": float(e.valor_bruto or 0),
            "liqPlat": float(e.valor_liquido or 0),
            "data": e.criado_em.strftime("%Y-%m-%d") if e.criado_em else "",
            "despesas": [{"nome": i.descricao, "valor": float(i.valor or 0)} for i in e.itens],
        })

    despesas_gerais_objs = DespesaGeral.query.filter_by(user_id=owner_id).order_by(DespesaGeral.data.desc()).all()
    for d in despesas_gerais_objs:
        lancamentos.append(_despesa_geral_para_lancamento(d, imovel_titulos.get(d.imovel_id, "")))

    lancamentos.sort(key=lambda d: d.get("entrada") or d.get("data") or "", reverse=True)

    return jsonify({
        "imoveis": [{"id": i.id, "titulo": i.titulo} for i in lista_imoveis],
        "lancamentos": lancamentos,
    })


@api_bp.route("/financas", methods=["POST"])
@api_login_required
def salvar_financas():
    owner_id = g.current_user.owner_id
    dados = request.get_json(silent=True) or {}

    try:
        financeiro_id = dados.get("id")

        if financeiro_id:
            financeiro = Financeiro.query.filter_by(id=financeiro_id, user_id=owner_id).first()
            if not financeiro:
                return jsonify({"success": False, "message": "Registro não encontrado"}), 404
        else:
            financeiro = Financeiro(user_id=owner_id)
            db.session.add(financeiro)

        entrada = datetime.strptime(dados["entrada"], "%Y-%m-%d").date() if dados.get("entrada") else None
        saida = datetime.strptime(dados["saida"], "%Y-%m-%d").date() if dados.get("saida") else None

        financeiro.imovel = dados.get("imovel")
        financeiro.site = dados.get("site")
        financeiro.status = dados.get("status")
        financeiro.bruto = float(dados.get("bruto", 0) or 0)
        financeiro.liq_plat = float(dados.get("liqPlat", 0) or 0)
        financeiro.entrada = entrada
        financeiro.saida = saida

        db.session.flush()

        FinanceiroDespesa.query.filter_by(financeiro_id=financeiro.id).delete()
        for despesa in dados.get("despesas", []):
            db.session.add(FinanceiroDespesa(
                financeiro_id=financeiro.id,
                nome=despesa.get("nome"),
                valor=float(despesa.get("valor", 0) or 0),
            ))

        db.session.commit()

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
                "despesas": [{"nome": d.nome, "valor": float(d.valor)} for d in financeiro.despesas],
            },
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@api_bp.route("/financas/<int:financeiro_id>", methods=["DELETE"])
@api_login_required
def excluir_financas(financeiro_id: int):
    owner_id = g.current_user.owner_id
    financeiro = Financeiro.query.filter_by(id=financeiro_id, user_id=owner_id).first()
    if not financeiro:
        return jsonify({"success": False, "message": "Registro não encontrado"}), 404

    FinanceiroDespesa.query.filter_by(financeiro_id=financeiro.id).delete()
    db.session.delete(financeiro)
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/despesas-gerais", methods=["POST"])
@api_login_required
def salvar_despesa_geral():
    owner_id = g.current_user.owner_id
    dados = request.get_json(silent=True) or {}

    try:
        try:
            imovel_id = int(dados.get("imovel_id"))
        except (TypeError, ValueError):
            imovel_id = None

        imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first() if imovel_id else None
        if not imovel:
            return jsonify({"success": False, "message": "Selecione um imóvel válido."}), 400

        categoria = (dados.get("categoria") or "").strip()
        nome = (dados.get("nome") or "").strip() or categoria
        if not categoria:
            return jsonify({"success": False, "message": "Selecione o que é essa despesa."}), 400
        if not nome:
            return jsonify({"success": False, "message": "Especifique a despesa."}), 400

        despesa_id = dados.get("id")
        if despesa_id:
            despesa = DespesaGeral.query.filter_by(id=despesa_id, user_id=owner_id).first()
            if not despesa:
                return jsonify({"success": False, "message": "Despesa não encontrada"}), 404
        else:
            despesa = DespesaGeral(user_id=owner_id)
            db.session.add(despesa)

        data_despesa = datetime.strptime(dados["data"], "%Y-%m-%d").date() if dados.get("data") else None

        despesa.imovel_id = imovel.id
        despesa.nome = nome
        despesa.categoria = categoria or None
        despesa.valor = float(dados.get("valor", 0) or 0)
        despesa.data = data_despesa or despesa.data or datetime.utcnow().date()
        despesa.observacoes = (dados.get("observacoes") or "").strip() or None

        db.session.commit()

        return jsonify({
            "success": True,
            "registro": _despesa_geral_para_lancamento(despesa, imovel.titulo),
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@api_bp.route("/despesas-gerais/<int:despesa_id>", methods=["DELETE"])
@api_login_required
def excluir_despesa_geral(despesa_id: int):
    owner_id = g.current_user.owner_id
    despesa = DespesaGeral.query.filter_by(id=despesa_id, user_id=owner_id).first()
    if not despesa:
        return jsonify({"success": False, "message": "Despesa não encontrada"}), 404

    try:
        db.session.delete(despesa)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


# ============================================================
# HUB DO ANFITRIÃO
# (núcleo operacional de app/routes/hub.py — score por imóvel, tarefas
#  de manutenção/limpeza/pilha. Reaproveita processar_lembretes() e
#  TIPOS_LEMBRETE de lá, sem alterar aquele arquivo. Lembretes/rotinas
#  recorrentes, eventos de precificação, eventos regionais e documentos
#  recebidos ainda não entraram nesta primeira versão do app — ficam pra
#  uma passada seguinte.
#
#  Rotas com nomes distintos das de app/routes/hub.py (que usa sessão de
#  cookie, não Bearer token) pra não colidir com elas: "/api/hub-tarefas"
#  em vez de "/api/hub/...".)
# ============================================================

@api_bp.route("/hub-tarefas", methods=["GET"])
@api_login_required
def hub_tarefas_dados():
    user = g.current_user
    owner_id = user.owner_id
    dono = user if not user.e_ajudante else db.session.get(User, owner_id)
    if dono:
        processar_lembretes(dono)

    imoveis = Imovel.query.filter_by(user_id=owner_id).all()
    hoje = date.today()

    proxima_estadia = (
        Estadia.query
        .filter(
            Estadia.user_id == owner_id,
            Estadia.status.in_(["confirmada", "em_andamento"]),
            Estadia.data_checkin >= hoje,
        )
        .order_by(Estadia.data_checkin.asc())
        .first()
    )
    proximo_checkin = None
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

    tarefas_abertas = (
        HubTarefa.query
        .filter_by(user_id=owner_id, concluida=False)
        .order_by(HubTarefa.created_at.desc())
        .limit(100)
        .all()
    )

    manutencoes_abertas = sum(1 for t in tarefas_abertas if t.tipo == "manutencao")
    limpezas_pendentes = sum(1 for t in tarefas_abertas if t.tipo == "limpeza_checkout")

    tarefas_abertas_por_imovel: dict = {}
    for t in tarefas_abertas:
        if t.imovel_id:
            tarefas_abertas_por_imovel.setdefault(t.imovel_id, []).append(t)

    dados_imoveis = []
    pilhas_vencidas = 0
    for im in imoveis:
        score = 100
        alertas = []

        # Mesma correção de app/routes/hub.py: só conta como alerta se o
        # anfitrião já registrou alguma troca de pilha pra esse imóvel.
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
            "score": score,
            "nivel": nivel,
            "alertas": alertas,
            "dias_pilha": dias_pilha if dias_pilha < 999 else None,
            "foto_principal": _url_foto(im.foto_principal),
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
            "criado_em": t.created_at.strftime("%d/%m/%Y %H:%M"),
            "data_prevista": t.data_prevista.isoformat() if t.data_prevista else None,
            "data_prevista_fmt": t.data_prevista.strftime("%d/%m/%Y") if t.data_prevista else None,
        })

    return jsonify({
        "total_imoveis": len(imoveis),
        "manutencoes_abertas": manutencoes_abertas,
        "limpezas_pendentes": limpezas_pendentes,
        "pilhas_vencidas": pilhas_vencidas,
        "tarefas_pendentes_total": len(tarefas_abertas),
        "proximo_checkin": proximo_checkin,
        "imoveis": dados_imoveis,
        "tarefas": tarefas_json,
    })


@api_bp.route("/hub-tarefas/manutencao", methods=["POST"])
@api_login_required
def hub_registrar_manutencao():
    owner_id = g.current_user.owner_id
    dados = request.get_json(silent=True) or {}

    imovel_id = dados.get("imovel_id")
    titulo = (dados.get("titulo") or "").strip()
    if not imovel_id or not titulo:
        return jsonify({"success": False, "message": "Imóvel e título são obrigatórios."}), 400

    imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first()
    if not imovel:
        return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    tarefa = HubTarefa(
        user_id=owner_id,
        imovel_id=imovel_id,
        titulo=titulo,
        descricao=dados.get("descricao", ""),
        tipo=dados.get("tipo") or "manutencao",
        concluida=False,
    )
    db.session.add(tarefa)
    db.session.commit()

    return jsonify({"success": True, "message": f"Registrado em {imovel.titulo}.", "tarefa_id": tarefa.id})


@api_bp.route("/hub-tarefas/troca-pilha/<int:imovel_id>", methods=["POST"])
@api_login_required
def hub_registrar_troca_pilha(imovel_id: int):
    owner_id = g.current_user.owner_id
    imovel = Imovel.query.filter_by(id=imovel_id, user_id=owner_id).first()
    if not imovel:
        return jsonify({"success": False, "message": "Imóvel não encontrado."}), 404

    imovel.ultima_troca_pilha = date.today()

    pendentes = HubTarefa.query.filter_by(
        user_id=owner_id, imovel_id=imovel_id, tipo="pilha_fechadura", concluida=False
    ).all()
    for t in pendentes:
        t.concluida = True

    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"Pilha de {imovel.titulo} registrada como trocada hoje.",
        "nova_data": imovel.ultima_troca_pilha.strftime("%d/%m/%Y"),
    })


@api_bp.route("/hub-tarefas/<int:tarefa_id>/concluir", methods=["POST"])
@api_login_required
def hub_concluir_tarefa(tarefa_id: int):
    owner_id = g.current_user.owner_id
    tarefa = HubTarefa.query.filter_by(id=tarefa_id, user_id=owner_id).first()
    if not tarefa:
        return jsonify({"success": False, "message": "Tarefa não encontrada."}), 404

    tarefa.concluida = not tarefa.concluida
    if tarefa.concluida and tarefa.tipo == "pilha_fechadura" and tarefa.imovel_id:
        imovel = db.session.get(Imovel, tarefa.imovel_id)
        if imovel:
            imovel.ultima_troca_pilha = date.today()

    db.session.commit()
    return jsonify({"success": True, "concluida": tarefa.concluida})


@api_bp.route("/hub-tarefas/<int:tarefa_id>", methods=["DELETE"])
@api_login_required
def hub_excluir_tarefa(tarefa_id: int):
    owner_id = g.current_user.owner_id
    tarefa = HubTarefa.query.filter_by(id=tarefa_id, user_id=owner_id).first()
    if not tarefa:
        return jsonify({"success": False, "message": "Tarefa não encontrada."}), 404

    db.session.delete(tarefa)
    db.session.commit()
    return jsonify({"success": True})


# ============================================================
# EQUIPE
# (mesma lógica de app/routes/equipe.py, devolvendo JSON. Só a conta
#  Proprietária — que não é ajudante de ninguém — pode gerenciar equipe.)
# ============================================================

def _anfitriao_publico(user: User) -> dict:
    return {
        "id": user.id,
        "nome": formatar_nome_exibicao(user.nome),
        "email": user.email,
        "foto": _url_foto_usuario(user.foto),
    }


def _convite_publico(convite: ConviteAnfitriao) -> dict:
    return {
        "id": convite.id,
        "email": convite.email,
        "status": convite.status,
        "criado_em": convite.created_at.strftime("%d/%m/%Y") if convite.created_at else "",
        "expirado": convite.expirado(),
    }


@api_bp.route("/equipe", methods=["GET"])
@api_login_required
def listar_equipe():
    user = g.current_user
    if user.e_ajudante:
        return jsonify({"erro": "Só a conta Proprietária pode gerenciar a equipe."}), 403

    anfitrioes = User.query.filter_by(proprietario_id=user.id).order_by(User.nome).all()
    convites_pendentes = (
        ConviteAnfitriao.query
        .filter_by(proprietario_id=user.id, status="pendente")
        .order_by(ConviteAnfitriao.created_at.desc())
        .all()
    )

    return jsonify({
        "anfitrioes": [_anfitriao_publico(a) for a in anfitrioes],
        "convites_pendentes": [_convite_publico(c) for c in convites_pendentes],
    })


@api_bp.route("/equipe/convidar", methods=["POST"])
@api_login_required
def convidar_anfitriao():
    user = g.current_user
    if user.e_ajudante:
        return jsonify({"erro": "Só a conta Proprietária pode convidar Anfitriões."}), 403

    dados = request.get_json(silent=True) or {}
    email = (dados.get("email") or "").strip().lower()
    if not email:
        return jsonify({"erro": "Informe um e-mail."}), 400
    if email == (user.email or "").strip().lower():
        return jsonify({"erro": "Você não pode convidar a si mesma(o)."}), 400

    convidado = User.query.filter_by(email=email).first()
    if convidado and convidado.proprietario_id == user.id:
        return jsonify({"erro": "Esse e-mail já é um Anfitrião da sua equipe."}), 400
    if convidado and convidado.e_ajudante:
        return jsonify({"erro": "Esse e-mail já está vinculado a outra conta Proprietária."}), 400

    ConviteAnfitriao.query.filter_by(
        proprietario_id=user.id, email=email, status="pendente"
    ).update({"status": "cancelado"})

    convite = ConviteAnfitriao(
        proprietario_id=user.id,
        email=email,
        token=ConviteAnfitriao.gerar_token(),
    )
    db.session.add(convite)
    db.session.commit()

    try:
        link = url_for("equipe.aceitar_convite_pagina", token=convite.token, _external=True)
        enviar_email_convite_anfitriao(
            destinatario=email,
            nome_proprietario=formatar_nome_exibicao(user.nome),
            link_convite=link,
            ja_tem_conta=bool(convidado),
        )
    except Exception:
        pass  # não bloqueia o fluxo se o e-mail falhar — o convite já existe

    return jsonify({"success": True, "message": f"Convite enviado para {email}.", "convite": _convite_publico(convite)}), 201


@api_bp.route("/equipe/convites/<int:convite_id>", methods=["DELETE"])
@api_login_required
def cancelar_convite_equipe(convite_id: int):
    user = g.current_user
    convite = ConviteAnfitriao.query.filter_by(id=convite_id, proprietario_id=user.id).first()
    if not convite:
        return jsonify({"erro": "Convite não encontrado."}), 404
    if convite.status != "pendente":
        return jsonify({"erro": "Esse convite não está mais pendente."}), 400

    convite.status = "cancelado"
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/equipe/anfitrioes/<int:anfitriao_id>", methods=["DELETE"])
@api_login_required
def remover_anfitriao_equipe(anfitriao_id: int):
    user = g.current_user
    ajudante = User.query.filter_by(id=anfitriao_id, proprietario_id=user.id).first()
    if not ajudante:
        return jsonify({"erro": "Anfitrião não encontrado na sua equipe."}), 404

    ajudante.proprietario_id = None
    db.session.commit()
    return jsonify({"success": True, "message": f"{formatar_nome_exibicao(ajudante.nome)} foi removido(a) da equipe."})


# ============================================================
# DASHBOARD DO PROPRIETÁRIO
# (mesma lógica de app/routes/main.py::dashboard_proprietario, devolvendo
#  JSON. Exclusivo da conta Proprietária, igual no site — um
#  Anfitrião-ajudante não vê o lucro real nem os custos configurados aqui.)
# ============================================================

@api_bp.route("/proprietario/dashboard", methods=["GET"])
@api_login_required
def proprietario_dashboard():
    user = g.current_user
    if user.e_ajudante:
        return jsonify({
            "erro": "O dashboard financeiro é exclusivo da conta Proprietária — "
                    "fale com quem te convidou para ver esses dados.",
        }), 403

    imoveis = Imovel.query.filter_by(user_id=user.id).all()

    hoje = datetime.utcnow()
    primeiro_dia_mes = hoje.replace(day=1).date()
    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    ultimo_dia_mes = (proximo_mes - timedelta(days=1)).date()

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
            "foto_principal": _url_foto(im.foto_principal),
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

    return jsonify({
        "imoveis": dados_imoveis,
        "consolidado": consolidado,
        "mes_referencia": hoje.strftime("%m/%Y"),
        "tem_imoveis": bool(imoveis),
        "tem_estadias": total_estadias_contabilizadas > 0,
    })


# ============================================================
# PERFIL / CONFIGURAÇÕES
# (mesma lógica de app/routes/usuario.py::usuario e
#  app/routes/main.py::salvar_configuracoes, devolvendo/recebendo JSON.
#  Upload de foto de perfil não entra nesta primeira versão do app.)
# ============================================================

def _perfil_completo(user: User) -> dict:
    return {
        "id": user.id,
        "nome": user.nome,
        "email": user.email,
        "telefone": user.telefone,
        "genero": user.genero,
        "data_nascimento": user.data_nascimento.strftime("%Y-%m-%d") if user.data_nascimento else None,
        "categoria": user.categoria,
        "e_ajudante": user.e_ajudante,
        "foto": _url_foto_usuario(user.foto),
        "theme": user.theme,
        "language": user.language,
        "currency": user.currency,
        "notify_browser": bool(user.notify_browser),
        "notify_email": bool(user.notify_email),
    }


@api_bp.route("/perfil", methods=["GET"])
@api_login_required
def ver_perfil():
    return jsonify({"perfil": _perfil_completo(g.current_user)})


@api_bp.route("/perfil", methods=["PUT"])
@api_login_required
def editar_perfil():
    user = g.current_user
    dados = request.get_json(silent=True) or {}

    if "nome" in dados:
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return jsonify({"erro": "O nome não pode ficar vazio."}), 400
        user.nome = nome

    if "email" in dados:
        email = (dados.get("email") or "").strip().lower()
        if not email:
            return jsonify({"erro": "O e-mail não pode ficar vazio."}), 400
        if email != user.email and User.query.filter_by(email=email).first():
            return jsonify({"erro": "Esse e-mail já está em uso."}), 400
        user.email = email

    if "telefone" in dados:
        user.telefone = (dados.get("telefone") or "").strip() or None

    if "genero" in dados:
        user.genero = (dados.get("genero") or "").strip() or None

    if "data_nascimento" in dados and dados.get("data_nascimento"):
        try:
            user.data_nascimento = datetime.strptime(dados["data_nascimento"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"erro": "Data de nascimento inválida."}), 400

    if "categoria" in dados:
        categoria_escolhida = (dados.get("categoria") or "").strip()
        if user.e_ajudante:
            user.categoria = "Anfitrião"
        elif categoria_escolhida in ("Anfitrião", "Proprietário"):
            user.categoria = categoria_escolhida

    db.session.commit()
    return jsonify({"perfil": _perfil_completo(user)})


@api_bp.route("/perfil/configuracoes", methods=["PUT"])
@api_login_required
def editar_configuracoes():
    user = g.current_user
    dados = request.get_json(silent=True) or {}

    theme = (dados.get("theme") or user.theme or "light").strip()
    language = (dados.get("language") or user.language or "pt-br").strip()
    currency = (dados.get("currency") or user.currency or "BRL").strip()

    if theme not in {"light", "dark", "auto"}:
        theme = "light"
    if language not in {"pt-br", "en", "es"}:
        language = "pt-br"
    if currency not in {"BRL", "USD", "EUR"}:
        currency = "BRL"

    user.theme = theme
    user.language = language
    user.currency = currency
    if "notify_browser" in dados:
        user.notify_browser = bool(dados.get("notify_browser"))
    if "notify_email" in dados:
        user.notify_email = bool(dados.get("notify_email"))

    db.session.commit()
    return jsonify({"perfil": _perfil_completo(user)})


@api_bp.route("/perfil", methods=["DELETE"])
@api_login_required
def excluir_conta_perfil():
    user = g.current_user
    try:
        email_usuario = user.email
        nome_usuario = formatar_nome_exibicao(user.nome)

        for imovel in user.imoveis:
            if imovel.foto_principal:
                from app.utils import deletar_arquivo
                deletar_arquivo(imovel.foto_principal)

        if user.foto:
            from app.utils import deletar_arquivo
            # user.foto é salvo como "uploads/<arquivo>" — deletar_arquivo
            # espera só o nome do arquivo (mesma convenção de Imovel.foto_principal).
            deletar_arquivo(user.foto.split("/", 1)[-1])

        db.session.delete(user)
        db.session.commit()

        try:
            enviar_email_despedida(email_usuario, nome_usuario)
        except Exception:
            pass

        return jsonify({"success": True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "erro": str(exc)}), 500


# ============================================================
# PAINEL MASTER (admin)
# (mesma lógica de app/routes/admin.py, devolvendo JSON. Exclusivo de
#  quem é is_admin (ou a conta master) — igual no site. Rotas com prefixo
#  "/api/painel-master" pra não colidir com as rotas web "/admin/...".)
# ============================================================

def _usuario_admin_publico(u: User) -> dict:
    return {
        "id": u.id,
        "nome": u.nome,
        "email": u.email,
        "categoria": u.categoria,
        "is_active": bool(u.is_active),
        "is_admin": bool(u.is_admin),
        "criado_em": u.created_at.strftime("%d/%m/%Y") if u.created_at else "",
    }


@api_bp.route("/painel-master/dashboard", methods=["GET"])
@api_admin_required
def painel_master_dashboard():
    today = date.today()
    start_month = today.replace(day=1)
    last_30_days = datetime.utcnow() - timedelta(days=30)

    total_usuarios = User.query.count()
    usuarios_ativos = User.query.filter_by(is_active=True).count()
    usuarios_admin = User.query.filter_by(is_admin=True).count()

    novos_mes = User.query.filter(User.created_at >= start_month).count()
    novos_30d = User.query.filter(User.created_at >= last_30_days).count()

    total_imoveis = Imovel.query.count()
    total_estadias = Estadia.query.count()

    faturamento_bruto_cents = (
        db.session.query(sa_func.sum(Estadia.valor_bruto_cents))
        .filter(Estadia.status != "cancelada")
        .scalar() or 0
    )
    faturamento_bruto = faturamento_bruto_cents / 100
    faturamento_formatado = _formatar_moeda(faturamento_bruto)

    estadias_hoje = Estadia.query.filter(
        Estadia.status != "cancelada",
        Estadia.data_checkin <= today,
        Estadia.data_checkout >= today,
    ).count()
    ocupacao = round((estadias_hoje / total_imoveis) * 100) if total_imoveis else 0

    usuarios_recentes = User.query.order_by(User.created_at.desc()).limit(8).all()

    labels = []
    users_by_month = []
    estadias_by_month = []
    now = datetime.utcnow()
    for i in range(11, -1, -1):
        month_start = (now.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        labels.append(month_start.strftime("%b/%y"))
        users_by_month.append(
            User.query.filter(User.created_at >= month_start, User.created_at < next_month).count()
        )
        estadias_by_month.append(
            Estadia.query.filter(Estadia.criado_em >= month_start, Estadia.criado_em < next_month).count()
        )

    return jsonify({
        "stats": {
            "total_usuarios": total_usuarios,
            "usuarios_ativos": usuarios_ativos,
            "usuarios_admin": usuarios_admin,
            "novos_mes": novos_mes,
            "novos_30d": novos_30d,
            "total_imoveis": total_imoveis,
            "total_estadias": total_estadias,
            "faturamento": faturamento_formatado,
            "ocupacao": ocupacao,
        },
        "usuarios_recentes": [_usuario_admin_publico(u) for u in usuarios_recentes],
        "chart": {
            "labels": labels,
            "users_by_month": users_by_month,
            "estadias_by_month": estadias_by_month,
        },
    })


@api_bp.route("/painel-master/usuarios", methods=["GET"])
@api_admin_required
def painel_master_usuarios():
    q = (request.args.get("q") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()

    query = User.query
    if q:
        query = query.filter(
            db.or_(
                sa_func.lower(User.nome).like(f"%{q}%"),
                sa_func.lower(User.email).like(f"%{q}%"),
            )
        )
    if status == "ativos":
        query = query.filter(User.is_active.is_(True))
    elif status == "inativos":
        query = query.filter(User.is_active.is_(False))

    usuarios = query.order_by(User.created_at.desc()).all()
    return jsonify({"usuarios": [_usuario_admin_publico(u) for u in usuarios]})


@api_bp.route("/painel-master/usuarios/<int:user_id>", methods=["PUT"])
@api_admin_required
def painel_master_editar_usuario(user_id: int):
    usuario = User.query.get_or_404(user_id)
    dados = request.get_json(silent=True) or {}

    if "nome" in dados:
        usuario.nome = dados.get("nome")
    if "email" in dados:
        usuario.email = dados.get("email")
    if "categoria" in dados:
        usuario.categoria = dados.get("categoria")
    if "is_active" in dados:
        usuario.is_active = bool(dados.get("is_active"))

    if usuario.email.lower() in ADMIN_EMAILS:
        usuario.is_admin = True
    elif "is_admin" in dados:
        usuario.is_admin = bool(dados.get("is_admin"))

    db.session.commit()
    return jsonify({"success": True, "usuario": _usuario_admin_publico(usuario)})


@api_bp.route("/painel-master/usuarios/<int:user_id>", methods=["DELETE"])
@api_admin_required
def painel_master_deletar_usuario(user_id: int):
    usuario = User.query.get_or_404(user_id)
    if usuario.email.lower() in ADMIN_EMAILS:
        return jsonify({"erro": "Você não pode deletar a conta master."}), 400

    db.session.delete(usuario)
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/painel-master/usuarios/<int:user_id>/toggle-ativo", methods=["POST"])
@api_admin_required
def painel_master_toggle_ativo(user_id: int):
    usuario = User.query.get_or_404(user_id)
    if usuario.email.lower() in ADMIN_EMAILS:
        return jsonify({"erro": "Você não pode desativar a conta master."}), 400

    usuario.is_active = not bool(usuario.is_active)
    db.session.commit()
    return jsonify({"success": True, "is_active": usuario.is_active})


@api_bp.route("/painel-master/usuarios/<int:user_id>/toggle-admin", methods=["POST"])
@api_admin_required
def painel_master_toggle_admin(user_id: int):
    usuario = User.query.get_or_404(user_id)
    if usuario.email.lower() in ADMIN_EMAILS:
        return jsonify({"erro": "A conta master sempre permanece admin."}), 400

    usuario.is_admin = not bool(usuario.is_admin)
    db.session.commit()
    return jsonify({"success": True, "is_admin": usuario.is_admin})


@api_bp.route("/painel-master/imoveis", methods=["GET"])
@api_admin_required
def painel_master_imoveis():
    imoveis = Imovel.query.order_by(Imovel.created_at.desc()).all()
    return jsonify({
        "imoveis": [
            {
                "id": im.id,
                "titulo": im.titulo,
                "endereco": im.endereco,
                "foto_principal": _url_foto(im.foto_principal),
                "user_id": im.user_id,
                "proprietario": im.proprietario.nome if im.proprietario else "",
                "criado_em": im.created_at.strftime("%d/%m/%Y") if im.created_at else "",
            }
            for im in imoveis
        ]
    })


@api_bp.route("/painel-master/imoveis/<int:imovel_id>", methods=["DELETE"])
@api_admin_required
def painel_master_deletar_imovel(imovel_id: int):
    imovel = Imovel.query.get_or_404(imovel_id)
    db.session.delete(imovel)
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/painel-master/financeiro", methods=["GET"])
@api_admin_required
def painel_master_financeiro():
    registros = Financeiro.query.order_by(Financeiro.data_registro.desc()).limit(200).all()

    faturamento_bruto = db.session.query(sa_func.sum(Financeiro.bruto)).scalar() or 0
    faturamento_liquido = db.session.query(sa_func.sum(Financeiro.liq_plat)).scalar() or 0
    total_registros = Financeiro.query.count()
    total_usuarios_financas = db.session.query(sa_func.count(sa_func.distinct(Financeiro.user_id))).scalar() or 0

    usuarios_map = {u.id: u for u in User.query.filter(
        User.id.in_([r.user_id for r in registros])
    ).all()} if registros else {}

    return jsonify({
        "registros": [
            {
                "id": r.id,
                "imovel": r.imovel,
                "usuario": usuarios_map[r.user_id].nome if r.user_id in usuarios_map else "",
                "site": r.site,
                "status": r.status,
                "bruto": float(r.bruto or 0),
                "liqPlat": float(r.liq_plat or 0),
                "data": r.data_registro.strftime("%d/%m/%Y") if r.data_registro else "",
            }
            for r in registros
        ],
        "faturamento_bruto": float(faturamento_bruto),
        "faturamento_liquido": float(faturamento_liquido),
        "total_registros": total_registros,
        "total_usuarios_financas": total_usuarios_financas,
    })
