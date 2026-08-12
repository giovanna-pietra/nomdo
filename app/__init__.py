"""
app/__init__.py
Application Factory — ponto central de criação da aplicação Flask.
"""

import os
import logging

from datetime import timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, request, session, redirect, url_for, g

from app.extensions import db, migrate, csrf, oauth, login_manager
from config import get_config


def create_app(config_name: str | None = None) -> Flask:
    """
    Cria e configura a instância Flask.
    """

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # =========================================================
    # CONFIG
    # =========================================================

    config_class = (
        get_config()
        if config_name is None
        else _config_by_name(config_name)
    )

    app.config.from_object(config_class)

    # =========================================================
    # GARANTE PASTA DE UPLOADS
    # =========================================================

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # =========================================================
    # EXTENSÕES
    # =========================================================

    _init_extensions(app)

    # =========================================================
    # GOOGLE OAUTH
    # =========================================================

    _register_google_oauth(app)

    # =========================================================
    # BLUEPRINTS
    # =========================================================

    _register_blueprints(app)

    # =========================================================
    # HEADERS GLOBAIS
    # =========================================================

    _register_after_request(app)

    # =========================================================
    # REFRESH AUTOMÁTICO DA SESSÃO
    # =========================================================

    @app.before_request
    def refresh_session():
        if "user_id" in session:
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=30)
            session.modified = True

    # =========================================================
    # PAYWALL — gate global de acesso (Asaas)
    # =========================================================

    @app.before_request
    def gate_paywall():
        """
        Bloqueia o acesso de quem ainda não pagou, redirecionando pra
        /pagamento — mas só quando PAYWALL_ATIVO=True (ou seja, só depois
        que uma chave real da Asaas for configurada). Até lá esse gate
        não faz nada, então nada muda pra quem já usa o sistema hoje.

        Donos/admins (is_admin) nunca são bloqueados.
        """
        if not app.config.get("PAYWALL_ATIVO"):
            return None

        endpoint = request.endpoint
        if not endpoint:
            return None

        # Rotas sempre livres: estáticos, autenticação, o próprio paywall,
        # cron interno e qualquer página pública acessada pelo hóspede
        # (guia digital, avaliação, formulário de documentos).
        # "main.index" ("/") de propósito NÃO está isenta aqui — pra quem
        # não está logado ela já é livre mesmo assim (sai cedo abaixo, sem
        # user_id na sessão); isentar também deixaria o logo do cabeçalho
        # (base_auth.html) virar um jeito de escapar do paywall sem pagar
        # (mesma brecha corrigida no gate_perfil_incompleto acima).
        blueprint_livre = {
            "static", "auth", "pagamento", "cron", "guia_publico",
            "documentos", "api",
        }
        endpoints_publicos = {
            "imoveis.pagina_publica_imovel",
            "imoveis.pagina_avaliacao_hospede",
            "imoveis.enviar_avaliacao_hospede",
        }

        blueprint_atual = endpoint.split(".")[0] if "." in endpoint else endpoint
        if blueprint_atual in blueprint_livre or endpoint in endpoints_publicos:
            return None

        user_id = session.get("user_id")
        if not user_id:
            return None  # sem sessão -> login_required de cada rota já cuida

        from app.models import User
        user = db.session.get(User, user_id)
        if not user:
            return None
        if user.is_admin:
            return None

        # Um Anfitrião-ajudante não paga por conta própria — o acesso
        # depende do pagamento da conta Proprietária a que está vinculado
        # (User.owner_id resolve pra si mesmo em contas independentes).
        dono = user if not user.e_ajudante else db.session.get(User, user.owner_id)
        if dono and (dono.is_admin or dono.pagamento_ativo):
            return None

        return redirect(url_for("pagamento.pagina_pagamento"))

    # =========================================================
    # PERFIL INCOMPLETO — gate global (telefone + data de nascimento + gênero)
    # =========================================================

    @app.before_request
    def gate_perfil_incompleto():
        """
        Exige telefone, data de nascimento e gênero em toda conta — contas
        criadas pelo Google nunca vêm com esses dados, e contas antigas de
        cadastro manual também podem estar sem eles (bug histórico do
        formulário, que nem sempre teve esses campos até essa correção).
        """
        endpoint = request.endpoint
        if not endpoint:
            return None

        blueprint_livre = {
            "static", "auth", "cron", "guia_publico",
            "documentos", "pagamento", "api",
        }
        # "main.index" (a home "/") NÃO entra aqui de propósito: pra quem
        # não está logado ela precisa ser livre mesmo, mas isso já é
        # garantido abaixo (sai cedo se não tem user_id na sessão) — deixar
        # "main.index" isento aqui também abria uma brecha real: o logo do
        # cabeçalho (base_auth.html) aponta pra "/", e como essa rota ficava
        # de fora do gate, dava pra clicar nela na tela de completar-perfil
        # e escapar sem preencher nada (main.index só redireciona pro
        # dashboard depois, sem passar pelo gate de novo no meio do caminho).
        endpoints_livres = {
            "usuario.completar_perfil", "usuario.excluir_conta",
        }

        blueprint_atual = endpoint.split(".")[0] if "." in endpoint else endpoint
        if blueprint_atual in blueprint_livre or endpoint in endpoints_livres:
            return None

        user_id = session.get("user_id")
        if not user_id:
            return None

        from app.models import User
        user = db.session.get(User, user_id)
        if not user:
            return None
        if user.is_admin:
            return None

        if not user.telefone or not user.data_nascimento or not user.genero:
            return redirect(url_for("usuario.completar_perfil"))

        return None

    # =========================================================
    # FILTRO DE MOEDA — {{ valor|moeda }} ou {{ valor|moeda(current_currency) }}
    # =========================================================

    from app.utils import formatar_moeda as _formatar_moeda_filtro

    def _filtro_moeda(valor, currency=None):
        moeda_atual = currency or getattr(g, "_moeda_atual", None)
        return _formatar_moeda_filtro(valor, moeda_atual)

    app.jinja_env.filters["moeda"] = _filtro_moeda

    @app.before_request
    def _definir_moeda_atual():
        """Guarda a moeda do usuário logado em `g` pro filtro `moeda`
        usar como padrão sem precisar passar currency em toda chamada."""
        user_id = session.get("user_id")
        if not user_id:
            g._moeda_atual = "BRL"
            return
        from app.models import User
        user = db.session.get(User, user_id)
        g._moeda_atual = getattr(user, "currency", None) or "BRL" if user else "BRL"

    # =========================================================
    # CONTEXTO GLOBAL PARA TEMPLATES
    # =========================================================

    @app.context_processor
    def inject_global_template_context():
        """
        Garante que templates que estendem `base_dash.html` tenham
        user/nome/categoria, inclusive no painel admin.

        `t`, `current_lang`, `currency_symbol` e `current_currency` ficam
        disponíveis em QUALQUER página — inclusive as públicas/sem sessão
        (login, cadastro, guia do hóspede etc.) — usando pt-br/BRL como
        padrão quando não há usuário logado.
        """
        from app.utils import formatar_nome_exibicao, get_translator, moeda_symbol
        from app.utils.i18n import IDIOMAS_SUPORTADOS

        try:
            from app.models import User

            user_id = session.get("user_id")
            user = db.session.get(User, user_id) if user_id else None

            if not user:
                # Sem sessão (login, cadastro, guia do hóspede etc.) — o
                # idioma vem do cookie setado pelo dropdown de bandeiras
                # (rota main.trocar_idioma), não do perfil salvo no banco.
                lang_visitante = request.cookies.get("nomdo_lang", "pt-br")
                if lang_visitante not in IDIOMAS_SUPORTADOS:
                    lang_visitante = "pt-br"
                return {
                    "current_lang": lang_visitante,
                    "t": get_translator(lang_visitante),
                    "current_currency": "BRL",
                    "currency_symbol": moeda_symbol("BRL"),
                }

            current_lang = getattr(user, "language", None) or "pt-br"
            current_currency = getattr(user, "currency", None) or "BRL"

            # ── E-mails automáticos ao hóspede (guia pré-estadia / pedido de
            #    avaliação) ─────────────────────────────────────────────────
            # Não há scheduler real neste projeto — aproveitamos qualquer
            # request autenticada do anfitrião para checar e disparar os
            # e-mails vencidos. Throttle de 5 min por sessão pra não bater
            # no banco em toda navegação.
            try:
                import time as _time
                agora = _time.time()
                ultimo_check = session.get("_ultimo_check_emails_hospede")
                if not ultimo_check or (agora - ultimo_check) > 300:
                    from app.services.hospede_notificacoes import processar_emails_hospede
                    from app.services.documentos_service import processar_formularios_documentos
                    # Os imóveis pertencem à conta Proprietária — se quem está
                    # logado é um Anfitrião-ajudante, processa em nome do
                    # Proprietário (user.owner_id), senão essas rotinas nunca
                    # disparariam pra imóveis geridos só por ajudantes.
                    dono_dados = user if not user.e_ajudante else db.session.get(User, user.owner_id)
                    if dono_dados:
                        processar_emails_hospede(dono_dados, request.host_url.rstrip("/"))
                        processar_formularios_documentos(dono_dados, request.host_url.rstrip("/"))
                    session["_ultimo_check_emails_hospede"] = agora
            except Exception:
                app.logger.exception("Falha ao processar e-mails automáticos ao hóspede")

            return {
                "user": user,
                "nome_usuario": formatar_nome_exibicao(user.nome),
                "nome_completo": user.nome,
                "categoria_usuario": user.categoria,
                "current_lang": current_lang,
                "t": get_translator(current_lang),
                "current_currency": current_currency,
                "currency_symbol": moeda_symbol(current_currency),
            }
        except Exception:
            return {
                "current_lang": "pt-br",
                "t": get_translator("pt-br"),
                "current_currency": "BRL",
                "currency_symbol": moeda_symbol("BRL"),
            }

    # =========================================================
    # LOGGING
    # =========================================================

    if not app.debug:
        _configure_logging(app)

    return app


# =============================================================
# HELPERS PRIVADOS
# =============================================================

def _config_by_name(name: str):
    from config.settings import config_map
    return config_map.get(name, config_map["production"])


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    oauth.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor, faça login para acessar esta página."
    login_manager.login_message_category = "info"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        from app import models
        if os.environ.get("AUTO_CREATE_DB", "False") == "True":
            db.create_all()


def _register_google_oauth(app: Flask) -> None:
    oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID", ""),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET", ""),
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )


def _register_blueprints(app: Flask) -> None:
    from app.routes import (
        auth_bp,
        main_bp,
        usuario_bp,
        imoveis_bp,
        reservas_bp,
        estadias_bp,
        suporte_bp,
        admin_bp,
        guia_publico_bp,
        hub_bp,
        cron_bp,
        pagamento_bp,
        documentos_bp,
        equipe_bp,
        api_bp,
        push_bp,
        limpezas_bp,
        manutencoes_bp,
        checklists_bp,
        documentos_recebidos_bp,
        rotinas_bp,
        precificacao_bp,
    )

    blueprints = [
        auth_bp,
        main_bp,
        usuario_bp,
        imoveis_bp,
        reservas_bp,
        estadias_bp,
        suporte_bp,
        admin_bp,
        guia_publico_bp,
        hub_bp,
        cron_bp,
        pagamento_bp,
        documentos_bp,
        equipe_bp,
        api_bp,
        push_bp,
        limpezas_bp,
        manutencoes_bp,
        checklists_bp,
        documentos_recebidos_bp,
        rotinas_bp,
        precificacao_bp,
    ]

    for bp in blueprints:
        app.register_blueprint(bp)


def _register_after_request(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def _configure_logging(app: Flask) -> None:
    os.makedirs("logs", exist_ok=True)
    handler = RotatingFileHandler(
        "logs/staykey.log",
        maxBytes=10_000_000,
        backupCount=5,
    )
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info("Nomdo iniciado.")
