"""
app/services/geocoding_service.py
Geocodificação de endereço via Google Geocoding API — um caminho de
backend adicional pra converter um endereço em texto livre em
lat/lng, pra usos que não dependem do navegador (ex.: importação em
lote de imóveis, validação server-side, ou alimentar outras APIs que
só aceitam coordenadas, como o Google Places em
app/services/eventos_service.py).

O autocomplete/geocodificação que já existe no formulário de cadastro
do imóvel (Nominatim/OpenStreetMap, 100% client-side — ver
_buscarNominatim/_autocompleteRuaNominatim em imoveis.html) CONTINUA
ativo e não é afetado por este módulo — este é um caminho a mais, não
uma substituição.

Sem GOOGLE_GEOCODING_API_KEY configurada, cai automaticamente pra
GOOGLE_MAPS_API_KEY (ver config/settings.py); sem nenhuma das duas,
geocodificar_endereco() devolve None em vez de quebrar — mesmo padrão
de degradação graciosa das outras integrações novas (Ticketmaster,
Foursquare etc.).

Docs: https://developers.google.com/maps/documentation/geocoding/overview
"""
from __future__ import annotations

import requests
from flask import current_app

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TIMEOUT_SEG = 8


def _api_key() -> str:
    return (current_app.config.get("GOOGLE_GEOCODING_API_KEY") or "").strip()


def geocodificar_endereco(endereco: str) -> dict | None:
    """
    Geocodifica um endereço em texto livre.

    Devolve {"lat": float, "lng": float, "endereco_formatado": str} ou
    None se a chave não estiver configurada, o endereço não for
    encontrado, ou a chamada falhar por qualquer motivo — nunca levanta
    exceção pro chamador, que só precisa tratar "sem resultado".
    """
    endereco = (endereco or "").strip()
    if not endereco:
        return None

    api_key = _api_key()
    if not api_key:
        return None

    try:
        resposta = requests.get(
            GEOCODING_URL,
            params={"address": endereco, "key": api_key},
            timeout=TIMEOUT_SEG,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.RequestException:
        current_app.logger.exception("Falha ao consultar Google Geocoding API")
        return None

    if dados.get("status") != "OK":
        return None

    resultados = dados.get("results") or []
    if not resultados:
        return None

    primeiro = resultados[0]
    localizacao = (primeiro.get("geometry") or {}).get("location") or {}
    lat, lng = localizacao.get("lat"), localizacao.get("lng")
    if lat is None or lng is None:
        return None

    return {
        "lat": lat,
        "lng": lng,
        "endereco_formatado": primeiro.get("formatted_address", endereco),
    }
