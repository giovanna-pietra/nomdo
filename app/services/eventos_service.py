"""
app/services/eventos_service.py
Agregador de "Eventos na Região" do Hub do Anfitrião — combina o que dá
pra buscar de verdade (Ticketmaster, Google Places) com um link de
busca manual pras plataformas que não têm API pública de descoberta
por região (Eventbrite, Sympla, Even3). Cada fonte é isolada com seu
próprio try/except: se uma falhar, as outras continuam funcionando
normalmente — nenhuma delas pode derrubar o Hub inteiro.

Diferente dos "Eventos de Precificação" (feriados/datas que o
anfitrião cadastra manualmente pra ajustar preço, ver
app/models/precificacao.py), isto aqui é sobre o que está acontecendo
DE FORA, perto do imóvel — informativo, não altera preço automaticamente.

─────────────────────────────────────────────────────────────────────
LEVANTAMENTO DE API (feito antes de implementar, documentado aqui pra
não repetir a pesquisa no futuro):

  Ticketmaster (Discovery API) — TEM busca por região (lat/lng + raio),
  tier gratuito, funciona pra terceiros. Já era usado no sistema antes
  desta task; só foi movido de app/routes/hub.py pra cá.

  Google Places (Nearby Search) — TEM busca por região. Mas não existe
  conceito de "evento com data marcada" na Places API — ela devolve
  LUGARES (pontos turísticos, atrações, casas de show como
  estabelecimento etc.), não agenda de shows/festivais. Por isso aqui
  ela entra como "lugares próximos" (buscar_lugares_google),
  complementando os eventos reais do Ticketmaster, não substituindo.

  Eventbrite — a API pública de descoberta de eventos por região foi
  DESCONTINUADA em 2019. Hoje a API só serve pra um organizador
  gerenciar os próprios eventos (não dá pra buscar eventos de
  terceiros por cidade sem ser parceiro comercial da Eventbrite).

  Sympla — a API pública documentada é só de gestão dos eventos do
  próprio organizador autenticado; não existe endpoint de busca por
  região pra terceiros.

  Even3 — não tem API pública documentada.

  Conclusão: Eventbrite/Sympla/Even3 ficam com EVENTBRITE_API_KEY/
  SYMPLA_API_KEY/EVEN3_API_KEY pré-prontas em config/settings.py pro
  dia em que isso mudar (parceria comercial, nova API pública etc.),
  mas por ora só recebem um link de busca (mesmo padrão já usado pro
  Ticketmaster quando TICKETMASTER_API_KEY não está configurada).
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from urllib.parse import quote_plus

import requests
from flask import current_app

TICKETMASTER_RAIO_KM = 60
TICKETMASTER_TIMEOUT_SEG = 6

GOOGLE_PLACES_RAIO_M = 8000
GOOGLE_PLACES_TIMEOUT_SEG = 6

# Domínios usados só pra montar o link de busca manual (ver
# links_busca_manual) — nenhuma chamada de API é feita pra eles.
_PLATAFORMAS_BUSCA_MANUAL = (
    ("eventbrite.com.br", "Eventbrite"),
    ("sympla.com.br", "Sympla"),
    ("even3.com.br", "Even3"),
)


# ─────────────────────────────────────────────────────────────────────
# Termo/link de busca (usado tanto pro Google genérico quanto pras
# plataformas sem API de descoberta por região)
# ─────────────────────────────────────────────────────────────────────

def _termo_busca(imovel) -> str:
    """
    Termo de busca pela CIDADE do imóvel, não pelo endereço/rua completo
    ("eventos na Rua X, 123" não traz nada útil no Google; "eventos em
    <cidade>" traz resultados de verdade).
    """
    cidade = (imovel.cidade or "").strip() if imovel else ""
    if cidade:
        # Cidade vem como "Cidade/UF" pra endereços do Brasil (ver
        # _selecionarCidade()/_buscarCEPImovel() em imoveis.html) — troca
        # a barra por vírgula pra virar uma busca natural.
        return f"eventos em {cidade.replace('/', ', ')}"
    if imovel and imovel.endereco:
        # Fallback pra imóveis antigos ainda sem cidade salva.
        return f"eventos em {imovel.endereco}"
    return "eventos na região"


def link_busca_google(imovel) -> str:
    """Link de busca genérico no Google — funciona sem nenhuma chave/API,
    complementa o que as integrações reais não tiverem (feiras locais,
    eventos pequenos etc.)."""
    return f"https://www.google.com/search?q={quote_plus(_termo_busca(imovel))}"


def links_busca_manual(imovel) -> list[dict]:
    """
    Um link de busca (via Google, com `site:`) pra cada plataforma sem
    API pública de descoberta por região (ver levantamento no topo do
    arquivo): Eventbrite, Sympla, Even3.
    """
    termo = _termo_busca(imovel)
    return [
        {
            "plataforma": dominio.split(".")[0],
            "nome": nome,
            "url": f"https://www.google.com/search?q={quote_plus(termo)}+site:{dominio}",
        }
        for dominio, nome in _PLATAFORMAS_BUSCA_MANUAL
    ]


# ─────────────────────────────────────────────────────────────────────
# Ticketmaster — eventos reais com data/hora marcada
# ─────────────────────────────────────────────────────────────────────

def buscar_eventos_ticketmaster(imovel) -> list[dict]:
    """
    Busca eventos (shows, feiras, festivais) num raio ao redor do
    imóvel via Ticketmaster Discovery API. Devolve lista vazia — nunca
    levanta exceção — se faltar TICKETMASTER_API_KEY, o imóvel não
    tiver lat/lng configurados, ou a chamada falhar.
    """
    if imovel is None or imovel.lat is None or imovel.lng is None:
        return []

    api_key = (current_app.config.get("TICKETMASTER_API_KEY") or "").strip()
    if not api_key:
        return []

    try:
        resp = requests.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={
                "apikey": api_key,
                "latlong": f"{imovel.lat},{imovel.lng}",
                "radius": TICKETMASTER_RAIO_KM,
                "unit": "km",
                "sort": "date,asc",
                "size": 12,
            },
            timeout=TICKETMASTER_TIMEOUT_SEG,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException:
        current_app.logger.exception("Falha ao consultar Ticketmaster Discovery API")
        return []

    eventos = []
    for ev in (payload.get("_embedded") or {}).get("events", []):
        datas = ev.get("dates", {}).get("start", {})
        venues = (ev.get("_embedded") or {}).get("venues", [])
        venue_nome = venues[0].get("name") if venues else None
        imagens = ev.get("images", [])
        imagem_url = imagens[0].get("url") if imagens else None
        eventos.append({
            "fonte": "ticketmaster",
            "nome": ev.get("name"),
            "data": datas.get("localDate"),
            "hora": datas.get("localTime"),
            "local": venue_nome,
            "url": ev.get("url"),
            "imagem": imagem_url,
        })
    return eventos


# ─────────────────────────────────────────────────────────────────────
# Google Places — lugares/pontos de interesse próximos (não é "evento"
# com data marcada, ver levantamento no topo do arquivo)
# ─────────────────────────────────────────────────────────────────────

def _url_google_maps_lugar(lugar: dict) -> str | None:
    place_id = lugar.get("place_id")
    if not place_id:
        return None
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def buscar_lugares_google(imovel) -> list[dict]:
    """
    Busca pontos turísticos/de interesse próximos ao imóvel via Google
    Places Nearby Search. Complementa os eventos com data marcada do
    Ticketmaster com sugestões do que existe na região (parques,
    atrações, pontos turísticos). Devolve lista vazia — nunca levanta
    exceção — se faltar a chave (GOOGLE_PLACES_API_KEY, com fallback
    automático pra GOOGLE_MAPS_API_KEY — ver config/settings.py), o
    imóvel não tiver lat/lng, ou a chamada falhar.
    """
    if imovel is None or imovel.lat is None or imovel.lng is None:
        return []

    api_key = (current_app.config.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if not api_key:
        return []

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{imovel.lat},{imovel.lng}",
                "radius": GOOGLE_PLACES_RAIO_M,
                "type": "tourist_attraction",
                "key": api_key,
            },
            timeout=GOOGLE_PLACES_TIMEOUT_SEG,
        )
        resp.raise_for_status()
        dados = resp.json()
    except requests.RequestException:
        current_app.logger.exception("Falha ao consultar Google Places Nearby Search")
        return []

    if dados.get("status") not in ("OK", "ZERO_RESULTS"):
        return []

    lugares = []
    for lugar in (dados.get("results") or [])[:12]:
        lugares.append({
            "fonte": "google_places",
            "nome": lugar.get("name"),
            "endereco": lugar.get("vicinity"),
            "nota": lugar.get("rating"),
            "avaliacoes": lugar.get("user_ratings_total"),
            "google_maps_url": _url_google_maps_lugar(lugar),
        })
    return lugares


# ─────────────────────────────────────────────────────────────────────
# Agregador principal — chamado pela rota (app/routes/hub.py)
# ─────────────────────────────────────────────────────────────────────

def agregar_eventos_regionais(imovel) -> dict:
    """
    Ponto de entrada único usado por GET /api/hub/eventos-regionais/<id>.
    Cada fonte roda isolada — se uma quebrar por um motivo inesperado
    (além dos já tratados dentro de cada função), as outras continuam
    disponíveis normalmente.
    """
    ticketmaster_configurado = bool((current_app.config.get("TICKETMASTER_API_KEY") or "").strip())
    eventos_ticketmaster: list[dict] = []
    if ticketmaster_configurado:
        try:
            eventos_ticketmaster = buscar_eventos_ticketmaster(imovel)
        except Exception:
            current_app.logger.exception("Falha isolada ao agregar eventos do Ticketmaster")

    google_places_configurado = bool((current_app.config.get("GOOGLE_PLACES_API_KEY") or "").strip())
    lugares_google: list[dict] = []
    if google_places_configurado:
        try:
            lugares_google = buscar_lugares_google(imovel)
        except Exception:
            current_app.logger.exception("Falha isolada ao agregar lugares do Google Places")

    return {
        "eventos": eventos_ticketmaster,
        "ticketmaster_configurado": ticketmaster_configurado,
        "lugares_proximos": lugares_google,
        "google_places_configurado": google_places_configurado,
        "busca_google_url": link_busca_google(imovel),
        "busca_manual": links_busca_manual(imovel),
    }
