"""
app/routes/auth.py
Blueprint de autenticação:
  - Login / Logout
  - Google OAuth
  - Cadastro + verificação de e-mail
  - Recuperação de senha
"""

from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    current_app,
)

from werkzeug.security import generate_password_hash

from app.extensions import db, oauth
from app.models import User

from app.utils import (
    usuario_logado,
    gerar_codigo,
    formatar_nome_exibicao,
    idade_minima_atingida,
    IDADE_MINIMA_CADASTRO,
    t_flash,
)

from app.extensions import db
from sqlalchemy.orm.attributes import flag_modified

from app.services import (
    enviar_codigo_verificacao,
    enviar_codigo_recuperacao,
)

auth_bp = Blueprint(
    "auth",
    __name__
)

ADMIN_EMAILS = ("grouppietra@gmail.com", "giovanna.perovano@pietragroup.com.br")


# ============================================================
# HELPERS
# ============================================================

def _tentar_aceitar_convite_pendente(user, token):
    """
    Se a pessoa chegou até aqui vindo de um link de convite de Anfitrião
    (/convite-anfitriao/<token>) sem estar logada, o token fica guardado em
    session["convite_token_pendente"] até ela logar ou criar a conta — aqui
    é onde processamos esse vínculo, assim que a sessão é criada.
    """
    from app.models import ConviteAnfitriao

    convite = ConviteAnfitriao.query.filter_by(token=token, status="pendente").first()
    if not convite or convite.expirado():
        return
    if convite.email.strip().lower() != (user.email or "").strip().lower():
        # Convite era pra outro e-mail — não vincula silenciosamente.
        return

    user.proprietario_id = convite.proprietario_id
    # Mesma regra de equipe.py: aceitar um convite trava a categoria
    # conforme o papel escolhido no convite ("Anfitrião" ou "Auxiliar"),
    # já que a pessoa passa a ser ajudante de outra conta.
    user.categoria = "Auxiliar" if convite.papel == "auxiliar" else "Anfitrião"
    convite.status = "aceito"
    convite.aceito_em = datetime.utcnow()
    convite.anfitriao_id = user.id
    db.session.commit()


def criar_sessao(user, remember=True):
    """
    Cria sessão persistente segura.
    """
    convite_token_pendente = session.get("convite_token_pendente")

    session.clear()

    # === CORREÇÃO CRUCIAL: FORÇAR ADMIN SEM APAGAR A CATEGORIA JÁ DEFINIDA ===
    if user.email and user.email.lower() in ADMIN_EMAILS:
        user.is_admin = True
        # Se o admin ainda não tiver nenhuma categoria definida, podemos dar um padrão,
        # mas se já tiver, nós NÃO tocamos nela mais!
        if not user.categoria:
            user.categoria = "Anfitrião"
            
        db.session.commit()

    session["user_id"] = user.id
    session["user_name"] = user.nome
    session["user_email"] = user.email  
    
    # Sincroniza a categoria de forma estrita no momento em que a sessão inicia
    session["user_categoria"] = user.categoria if user.categoria else ""

    session["is_admin"] = bool(getattr(user, "is_admin", False)) or (
        user.email.lower() in ADMIN_EMAILS
    )
    
    # Login persistente
    session.permanent = bool(remember)

    # Se a pessoa chegou aqui vinda de um convite de Anfitrião pendente
    # (ver app/routes/equipe.py), vincula agora que a sessão já existe.
    if convite_token_pendente:
        _tentar_aceitar_convite_pendente(user, convite_token_pendente)
        # A categoria pode ter mudado pra "Anfitrião" dentro da função acima
        # (convite aceito) — resincroniza o valor já gravado na sessão.
        session["user_categoria"] = user.categoria if user.categoria else ""


# ============================================================
# LOGIN
# ============================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if usuario_logado():
        return redirect(
            url_for("reservas.dashboard")
        )

    if request.method == "POST":
        email = (
            request.form
            .get("email", "")
            .strip()
            .lower()
        )

        senha = request.form.get(
            "senha",
            ""
        )

        remember = request.form.get(
            "remember"
        )

        user = User.query.filter_by(
            email=email
        ).first()

        # ====================================================
        # LOGIN NORMAL
        # ====================================================
        if (
            user
            and user.auth_provider == "email"
            and user.verificar_senha(senha)
        ):

            if not user.is_confirmed:
                flash(
                    t_flash("Por favor, confirme seu e-mail antes de entrar."),
                    "erro"
                )
                return redirect(
                    url_for("auth.login")
                )

            # Força a atualização do cache do SQLAlchemy antes de logar
            db.session.refresh(user)

            criar_sessao(
                user=user,
                remember=remember
            )
            user.last_login_at = datetime.utcnow()
            db.session.commit()

            flash(
                t_flash("Bem-vindo(a), %(nome)s!", nome=formatar_nome_exibicao(user.nome)),
                "sucesso"
            )

            return redirect(
                url_for("reservas.dashboard")
            )

        # ====================================================
        # LOGIN FALHOU — mensagens específicas por motivo
        # ====================================================
        if not user:
            flash(
                t_flash("Esse e-mail não está cadastrado. Verifique se digitou certo ou crie uma conta."),
                "erro"
            )
        elif user.auth_provider != "email":
            flash(
                t_flash("Essa conta foi criada com login do Google. Entre usando o botão \"Entrar com Google\"."),
                "erro"
            )
        else:
            flash(
                t_flash("E-mail ou senha incorretos."),
                "erro"
            )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================
# (O paywall agora é feito pelo gate global em app/__init__.py —
#  ver app/routes/pagamento.py — em vez de um decorator por rota.)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(
        url_for("auth.login")
    )


# ============================================================
# GOOGLE LOGIN
# ============================================================

@auth_bp.route("/login/google")
def login_google():
    redirect_uri = url_for(
        "auth.google_callback",
        _external=True
    )
    return oauth.google.authorize_redirect(
        redirect_uri,
        prompt="select_account consent"
    )


@auth_bp.route("/login/google/callback")
def google_callback():
    try:
        oauth.google.authorize_access_token()
        user_info = oauth.google.get(
            "https://openidconnect.googleapis.com/v1/userinfo"
        ).json()
    except Exception as exc:
        current_app.logger.error(
            "Erro OAuth Google: %s",
            exc
        )
        flash(
            t_flash("Erro ao autenticar com Google."),
            "erro"
        )
        return redirect(
            url_for("auth.login")
        )

    email = (
        user_info
        .get("email", "")
        .strip()
        .lower()
    )

    nome = user_info.get(
        "name",
        "Usuário Google"
    )

    user = User.query.filter_by(
        email=email
    ).first()

    # ========================================================
    # CRIA USUÁRIO SE NÃO EXISTIR
    # ========================================================
    if not user:
        user = User(
            nome=nome,
            email=email,
            is_confirmed=True,
            auth_provider="google",
        )
        user._senha = ""
        user.categoria = "Anfitrião"
        db.session.add(user)
        db.session.commit()
    else:
        db.session.refresh(user)

    criar_sessao(
        user=user,
        remember=True
    )
    user.last_login_at = datetime.utcnow()
    
    if hasattr(user, 'categoria') and user.categoria:
        flag_modified(user, "categoria")

    db.session.commit()

    return redirect(
        url_for("usuario.usuario")
    )


# ============================================================
# CADASTRO
# ============================================================

@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():

    if request.method == "POST":
        nome = request.form.get("name", "").strip()

        email = (
            request.form
            .get("email", "")
            .strip()
            .lower()
        )

        telefone = (request.form.get("telefone_completo") or "").strip()
        senha = request.form.get("senha", "")
        genero = (request.form.get("genero") or "").strip()
        data_nascimento = (request.form.get("data_nascimento") or "").strip()

        # Validação obrigatória server-side: telefone e data de nascimento
        # (além dos demais campos básicos) são exigidos em toda conta nova,
        # criada por cadastro manual ou por Google (ver completar-perfil).
        campos_faltando = []
        if not nome:
            campos_faltando.append(t_flash("nome"))
        if not email:
            campos_faltando.append(t_flash("e-mail"))
        if not senha or len(senha) < 8:
            campos_faltando.append(t_flash("senha (mínimo 8 caracteres)"))
        if not genero:
            campos_faltando.append(t_flash("gênero"))
        if not data_nascimento:
            campos_faltando.append(t_flash("data de nascimento"))
        if not telefone:
            campos_faltando.append(t_flash("telefone"))

        if campos_faltando:
            flash(
                t_flash("Preencha todos os campos obrigatórios: %(campos)s.", campos=", ".join(campos_faltando)),
                "erro"
            )
            return redirect(
                url_for("auth.cadastro")
            )

        # Idade mínima de cadastro (13 anos) — vale tanto pra quem se
        # cadastra por aqui quanto por Google (nesse caso a checagem
        # acontece em completar-perfil, já que o Google não manda a data
        # de nascimento no login).
        if not idade_minima_atingida(data_nascimento):
            flash(
                t_flash("Você precisa ter pelo menos %(idade)s anos para se cadastrar.", idade=IDADE_MINIMA_CADASTRO),
                "erro"
            )
            return redirect(
                url_for("auth.cadastro")
            )

        if User.query.filter_by(
            email=email
        ).first():
            flash(
                t_flash("E-mail já cadastrado."),
                "erro"
            )
            return redirect(
                url_for("auth.cadastro")
            )

        codigo = gerar_codigo()

        session["cadastro_temp"] = {
            "nome": nome,
            "cpf": request.form.get("cpf"),
            "email": email,
            "telefone": telefone,
            # Cadastro público removeu a opção "Hóspede" — todo mundo que se
            # cadastra aqui é Anfitrião (a hierarquia Proprietário/Anfitrião
            # vem numa fase seguinte da reformulação).
            "categoria": "Anfitrião",
            "senha_hash": generate_password_hash(senha),
            "genero": genero,
            "data_nascimento": data_nascimento,
            "codigo": codigo,
        }

        enviar_codigo_verificacao(
            email,
            session["cadastro_temp"]["nome"],
            codigo
        )

        return redirect(
            url_for("auth.verificar_codigo")
        )

    return render_template(
        "cadastro.html"
    )


# ============================================================
# VERIFICAÇÃO
# ============================================================

@auth_bp.route("/verificar-codigo", methods=["GET", "POST"])
def verificar_codigo():
    dados = session.get(
        "cadastro_temp"
    )

    if not dados:
        return redirect(
            url_for("auth.cadastro")
        )

    if request.method == "POST":
        codigo_digitado = (
            request.form
            .get("codigo", "")
            .strip()
        )

        if codigo_digitado == dados["codigo"]:
            data_nasc = None
            if dados.get("data_nascimento"):
                data_nasc = datetime.strptime(
                    dados["data_nascimento"],
                    "%Y-%m-%d"
                ).date()

            novo_user = User(
                nome=dados["nome"],
                cpf=dados.get("cpf"),
                email=dados["email"],
                telefone=dados.get("telefone"),
                categoria=dados.get("categoria"),
                genero=dados.get("genero"),
                data_nascimento=data_nasc,
                is_confirmed=True,
            )
            novo_user._senha = dados["senha_hash"]

            db.session.add(novo_user)
            db.session.commit()

            session.pop(
                "cadastro_temp",
                None
            )

            db.session.refresh(novo_user)

            criar_sessao(
                user=novo_user,
                remember=True
            )

            flash(
                t_flash("Cadastro realizado com sucesso!"),
                "sucesso"
            )

            return redirect(
                url_for("reservas.dashboard")
            )

        flash(
            t_flash("Código inválido."),
            "erro"
        )

    return render_template(
        "verificar_codigo.html",
        email=dados["email"]
    )


# ============================================================
# ESQUECI SENHA
# ============================================================

@auth_bp.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():

    if request.method == "POST":
        email = (
            request.form
            .get("email", "")
            .strip()
            .lower()
        )

        user = User.query.filter_by(
            email=email
        ).first()

        if user:
            codigo = gerar_codigo()
            user.codigo_verificacao = codigo
            db.session.commit()

            enviar_codigo_recuperacao(
                email,
                user.nome,
                codigo
            )

            return redirect(
                url_for(
                    "auth.resetar_senha",
                    email=email
                )
            )

        flash(
            t_flash("E-mail não encontrado."),
            "erro"
        )

    return render_template(
        "esqueci_senha.html"
    )


# ============================================================
# RESETAR SENHA
# ============================================================

@auth_bp.route("/resetar-senha", methods=["GET", "POST"])
def resetar_senha():
    email = request.args.get(
        "email",
        ""
    )

    if request.method == "POST":
        user = User.query.filter_by(
            email=email
        ).first()

        codigo = (
            request.form
            .get("codigo", "")
            .strip()
        )

        if (
            user
            and user.codigo_verificacao == codigo
        ):
            nova_senha = request.form.get(
                "senha",
                ""
            )

            user._senha = generate_password_hash(
                nova_senha
            )
            user.codigo_verificacao = None
            db.session.commit()

            db.session.refresh(user)

            criar_sessao(
                user=user,
                remember=True
            )

            flash(
                t_flash("Senha alterada com sucesso!"),
                "sucesso"
            )

            return redirect(
                url_for("reservas.dashboard")
            )

        flash(
            t_flash("Código inválido."),
            "erro"
        )

    return render_template(
        "resetar_senha.html",
        email=email
    )