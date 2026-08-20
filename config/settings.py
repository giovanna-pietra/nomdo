"""
config/settings.py
Configurações centralizadas por ambiente.
Lidas via variáveis de ambiente (nunca hardcoded).
"""

from dotenv import load_dotenv
load_dotenv()

import os
from datetime import timedelta


def _require(key: str) -> str:
    """
    Lê variável obrigatória;
    lança erro claro se ausente.
    """

    value = os.environ.get(key)

    if not value:

        raise RuntimeError(
            f"[CONFIG] Variável de ambiente obrigatória não definida: {key}\n"
            f"Copie .env.example para .env e preencha o valor."
        )

    return value


class BaseConfig:
    """
    Configurações comuns a todos os ambientes.
    """

    # =========================================================
    # FLASK
    # =========================================================

    SECRET_KEY: str = _require("SECRET_KEY")

    DEBUG = False

    # =========================================================
    # SESSÃO / LOGIN PERSISTENTE
    # =========================================================

    # Sessão permanente
    SESSION_PERMANENT = True

    # Renova a sessão automaticamente a cada request
    SESSION_REFRESH_EACH_REQUEST = True

    # Expira apenas após inatividade
    PERMANENT_SESSION_LIFETIME = timedelta(
        days=int(
            os.environ.get(
                "PERMANENT_SESSION_LIFETIME_DAYS",
                90
            )
        )
    )

    # Nome do cookie
    SESSION_COOKIE_NAME = "staykey_session"

    # Segurança do cookie
    SESSION_COOKIE_HTTPONLY = True

    # Proteção CSRF básica
    SESSION_COOKIE_SAMESITE = os.environ.get(
        "SESSION_COOKIE_SAMESITE",
        "Lax"
    )

    # True apenas em HTTPS/produção
    SESSION_COOKIE_SECURE = False

    # =========================================================
    # BANCO DE DADOS
    # =========================================================

    SQLALCHEMY_DATABASE_URI: str = _require(
        "DATABASE_URL"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {

        # Reconecta automaticamente
        "pool_pre_ping": True,

        # Recicla conexões antigas
        "pool_recycle": 300,

        # Pool base
        "pool_size": 10,

        # Overflow permitido
        "max_overflow": 20,
    }

    # =========================================================
    # UPLOADS
    # =========================================================

    BASE_DIR = os.path.abspath(
        os.path.dirname(__file__)
    )

    BASE_DIR = os.path.dirname(BASE_DIR)

    UPLOAD_FOLDER = os.path.join(
        BASE_DIR,
        "app",
        "static",
        "uploads"
    )

    # Documentos sensíveis do hóspede (RG/CPF, foto do pet etc. — ver
    # app/routes/documentos.py) NÃO ficam em app/static: essa pasta fica
    # fora da árvore servida publicamente pelo Flask, e só é acessível via
    # rota protegida (documentos_recebidos.servir_arquivo), que confere
    # login + posse do imóvel antes de mostrar a imagem. Antes, esses
    # arquivos iam pra UPLOAD_FOLDER (público) — qualquer um com a URL
    # exata conseguia ver, sem exigir login nenhum.
    UPLOAD_FOLDER_DOCUMENTOS = os.path.join(
        BASE_DIR,
        "uploads_privados",
        "documentos"
    )

    # 5MB
    MAX_CONTENT_LENGTH = int(
        os.environ.get(
            "MAX_CONTENT_LENGTH",
            5 * 1024 * 1024
        )
    )

    # Extensões permitidas
    ALLOWED_EXTENSIONS = {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "pdf",
        "doc",
        "docx",
        "txt"
    }

    # =========================================================
    # GOOGLE OAUTH
    # =========================================================

    GOOGLE_CLIENT_ID = os.environ.get(
        "GOOGLE_CLIENT_ID",
        ""
    )

    GOOGLE_CLIENT_SECRET = os.environ.get(
        "GOOGLE_CLIENT_SECRET",
        ""
    )

    # =========================================================
    # EMAIL
    # =========================================================

    EMAIL_REMETENTE = os.environ.get(
        "EMAIL_REMETENTE",
        ""
    )

    EMAIL_SENHA = os.environ.get(
        "EMAIL_SENHA",
        ""
    )

    # =========================================================
    # GOOGLE MAPS (widget "O que fazer por perto" no guia do hóspede)
    # Sem GOOGLE_MAPS_API_KEY configurada, a seção de mapa/lugares
    # próximos simplesmente não aparece no guia — não quebra a página.
    # Precisa ter Maps JavaScript API + Places API ativadas e
    # faturamento habilitado no Google Cloud Console.
    # =========================================================

    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    # Chaves dedicadas para geocodificação de endereço (backend, ver
    # app/services/geocoding_service.py) e para busca de lugares/eventos
    # próximos via Google Places (ver app/services/eventos_service.py).
    # Se não forem preenchidas, cada uma cai de volta pra
    # GOOGLE_MAPS_API_KEY acima — só é obrigatório configurar chaves
    # separadas se quiser restringir/faturar cada uso isoladamente no
    # Google Cloud Console (recomendado em produção, opcional em dev).
    GOOGLE_GEOCODING_API_KEY = os.environ.get("GOOGLE_GEOCODING_API_KEY", "") or GOOGLE_MAPS_API_KEY
    GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "") or GOOGLE_MAPS_API_KEY

    # =========================================================
    # EVENTOS — plataformas adicionais (ver app/services/eventos_service.py)
    #
    # Eventbrite: API pública de descoberta de eventos por região foi
    # descontinuada em 2019 (hoje só serve pra organizador gerenciar os
    # próprios eventos) — sem parceria comercial não dá pra buscar eventos
    # de terceiros por cidade. EVENTBRITE_API_KEY fica pré-pronta pra
    # quando isso mudar ou surgir acesso de parceiro; até lá o agregador
    # mostra só um link de busca manual no site da Eventbrite.
    #
    # Sympla: a API pública é só de gestão dos eventos do próprio
    # organizador logado, não existe busca por região pra terceiros.
    # SYMPLA_API_KEY fica pré-pronta pelo mesmo motivo; até lá, link de
    # busca manual.
    #
    # Even3: não tem API pública documentada. EVEN3_API_KEY fica pré-pronta
    # como placeholder; até existir uma API oficial, link de busca manual.
    # =========================================================

    EVENTBRITE_API_KEY = os.environ.get("EVENTBRITE_API_KEY", "")
    SYMPLA_API_KEY = os.environ.get("SYMPLA_API_KEY", "")
    EVEN3_API_KEY = os.environ.get("EVEN3_API_KEY", "")

    # =========================================================
    # TICKETMASTER (eventos regionais no Hub do Anfitrião)
    # Sem TICKETMASTER_API_KEY configurada, a seção de eventos mostra só o
    # link de busca no Google — não quebra a página. Tem tier gratuito
    # (Discovery API): https://developer.ticketmaster.com/
    # =========================================================

    TICKETMASTER_API_KEY = os.environ.get("TICKETMASTER_API_KEY", "")

    # =========================================================
    # FOURSQUARE PLACES (estrelas/nº de avaliações em "O que fazer por
    # perto" no guia do hóspede). Sem FOURSQUARE_API_KEY configurada, essa
    # seção continua funcionando com OpenStreetMap (nome, categoria e
    # distância), só sem nota/avaliação — não quebra a página.
    # A chave é feita sempre no BACKEND (nunca aparece no HTML/JS do guia,
    # que é uma página pública sem login), pra não vazar a chave da conta.
    # Tem plano gratuito, sem cartão de crédito: https://location.foursquare.com/developer/
    # =========================================================

    FOURSQUARE_API_KEY = os.environ.get("FOURSQUARE_API_KEY", "")

    # =========================================================
    # CRON (checagens diárias agendadas externamente — pilha,
    # limpeza, e-mails ao hóspede). Sem CRON_SECRET definido, o
    # endpoint /api/cron/processar-lembretes fica desativado.
    # =========================================================

    CRON_SECRET = os.environ.get(
        "CRON_SECRET",
        ""
    )

    # URL pública do site, usada para montar os links dos e-mails
    # quando o cron chama o endpoint (opcional — se vazio, usa o
    # host da própria requisição).
    APP_BASE_URL = os.environ.get(
        "APP_BASE_URL",
        ""
    )

    # =========================================================
    # PAYWALL (Asaas) — assinatura mensal recorrente, pré-pronta mas
    # desativada por padrão. Sem ASAAS_API_KEY configurada, o sistema
    # continua liberado pra todo mundo (equivalente a como funciona hoje).
    # Quando a chave real da Asaas estiver disponível, defina
    # PAYWALL_ATIVO=True no ambiente pra passar a exigir a assinatura.
    #
    # Planos por quantidade de imóveis do Proprietário (ver
    # app/services/planos.py — PLANOS é a fonte da verdade, os valores
    # abaixo só configuram os preços de cada faixa):
    #   até 5 imóveis   -> "ate_5"   -> PLANO_ATE_5_CENTS   (padrão R$ 20,00)
    #   até 10 imóveis  -> "ate_10"  -> PLANO_ATE_10_CENTS  (padrão R$ 35,00)
    #   11+ imóveis     -> "mais_10" -> PLANO_MAIS_10_CENTS (padrão R$ 50,00)
    # =========================================================

    PAYWALL_ATIVO = os.environ.get("PAYWALL_ATIVO", "False") == "True"

    ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY", "")

    # "sandbox" (ambiente de testes da Asaas) ou "production"
    ASAAS_ENV = os.environ.get("ASAAS_ENV", "sandbox")

    # Segredo compartilhado pra validar o webhook da Asaas (mesmo padrão
    # do CRON_SECRET). Configure o mesmo valor no painel da Asaas ao
    # cadastrar a URL do webhook (/webhooks/asaas).
    ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")

    PLANO_ATE_5_CENTS = int(os.environ.get("PLANO_ATE_5_CENTS", 2000))
    PLANO_ATE_10_CENTS = int(os.environ.get("PLANO_ATE_10_CENTS", 3500))
    PLANO_MAIS_10_CENTS = int(os.environ.get("PLANO_MAIS_10_CENTS", 5000))

    # =========================================================
    # NOTIFICAÇÕES PUSH NO NAVEGADOR (Web Push / VAPID)
    # Sem VAPID_PUBLIC_KEY + VAPID_PRIVATE_KEY configuradas, o toggle
    # "Notificações no Navegador" em Configurações simplesmente não
    # consegue se inscrever (a página avisa e não quebra nada). Gere um
    # par de chaves com:
    #   python -c "from py_vapid import Vapid02; import base64; v=Vapid02(); v.generate_keys(); ..."
    # ou instale `pywebpush` e rode `vapid --gen`.
    # =========================================================

    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")

    # E-mail de contato exigido pelo protocolo Web Push (vai no header
    # Authorization como "mailto:..." — os provedores de push usam isso
    # pra falar com quem está mandando notificação em caso de abuso).
    VAPID_ADMIN_EMAIL = os.environ.get("VAPID_ADMIN_EMAIL", "")

    # =========================================================
    # CSRF
    # =========================================================

    WTF_CSRF_ENABLED = True


# =============================================================
# DEVELOPMENT
# =============================================================

class DevelopmentConfig(BaseConfig):

    DEBUG = True

    FLASK_DEBUG = True

    SESSION_COOKIE_SECURE = False

    # facilita testes locais
    WTF_CSRF_ENABLED = False


# =============================================================
# PRODUCTION
# =============================================================

class ProductionConfig(BaseConfig):

    DEBUG = False

    FLASK_DEBUG = False

    # HTTPS obrigatório em produção
    SESSION_COOKIE_SECURE = (
        os.environ.get(
            "SESSION_COOKIE_SECURE",
            "True"
        ) == "True"
    )


# =============================================================
# TESTING
# =============================================================

class TestingConfig(BaseConfig):

    TESTING = True

    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    WTF_CSRF_ENABLED = False

    SESSION_COOKIE_SECURE = False


# =============================================================
# MAPA DE CONFIGS
# =============================================================

config_map = {

    "development": DevelopmentConfig,

    "production": ProductionConfig,

    "testing": TestingConfig,
}


# =============================================================
# GET CONFIG
# =============================================================

def get_config() -> type:

    env = os.environ.get(
        "FLASK_ENV",
        "production"
    )

    return config_map.get(
        env,
        ProductionConfig
    )