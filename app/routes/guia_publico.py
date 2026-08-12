"""
app/routes/guia_publico.py

Rotas PÚBLICAS do guia digital do hóspede (acessadas via QR code).
Propositalmente SEM @login_required — quem escaneia o QR não tem
conta no Nomdo.

Regra de ouro deste arquivo: NUNCA importar/expor campos financeiros,
de outras estadias ou de outros hóspedes. Só o que é seguro mostrar
para um estranho com o link em mãos.
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Blueprint, render_template, jsonify, abort, current_app, request

from app.models import Imovel

guia_publico_bp = Blueprint("guia_publico", __name__)


# ── Helpers de parsing (mesma lógica de imoveis.py, sem duplicar import) ──────

def _parse_utensilios(raw):
    if not raw or not raw.strip() or raw.strip() in ("[]", "null", ""):
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [u for u in parsed if isinstance(u, dict) and u.get("nome")]
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"nome": u.strip(), "valor": ""} for u in raw.split(",") if u.strip()]


def _parse_regras(raw):
    if not raw or not raw.strip() or raw.strip() in ("[]", "null", ""):
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict) and r.get("texto")]
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"texto": r.strip(), "horario_inicio": "", "horario_fim": "", "multa": ""} for r in raw.split("\n") if r.strip()]


def _buscar_imovel_publico(slug: str) -> Imovel:
    """
    Busca o imóvel pelo slug público (não pelo id sequencial).
    Usar o id direto na URL pública deixaria fácil enumerar
    /g/1, /g/2, /g/3... e vazar wifi/fechadura de outros anfitriões.
    """
    imovel = Imovel.query.filter_by(slug_publico=slug).first()
    if not imovel:
        abort(404)
    return imovel


# ── Página do guia (HTML) ─────────────────────────────────────────────────────

@guia_publico_bp.route("/g/<slug>")
def guia_hospede(slug):
    imovel = _buscar_imovel_publico(slug)
    google_maps_api_key = current_app.config.get("GOOGLE_MAPS_API_KEY", "")
    foursquare_disponivel = bool(current_app.config.get("FOURSQUARE_API_KEY", ""))
    return render_template(
        "guia_hospede.html", imovel=imovel, google_maps_api_key=google_maps_api_key,
        foursquare_disponivel=foursquare_disponivel,
    )


# ── Locais próximos com avaliação real (Foursquare Places) ───────────────────
#
# O mapa e a busca "por categoria" em si já funcionam de graça via
# OpenStreetMap (sem chave nenhuma) — isso aqui é só um upgrade OPCIONAL:
# quando existe FOURSQUARE_API_KEY configurada, essa rota busca os mesmos
# locais só que com nota/nº de avaliações reais, que o OpenStreetMap não
# tem. A chave nunca é exposta pro navegador do hóspede: essa chamada é
# toda feita aqui no backend, e o guia (JS público) só recebe o resultado
# já pronto, sem nenhum dado sensível.
#
# IMPORTANTE: os campos "rating"/"stats" são classificados pela Foursquare
# como "Places Premium" na documentação deles — pode ser que não venham
# preenchidos dependendo do plano da chave (o plano gratuito/pay-as-you-go
# cobre os campos "Pro": nome, endereço, distância etc, mas nota/avaliação
# às vezes exige um tier pago). Se vier vazio, o guia simplesmente não
# mostra estrelas pra aquele local — não trava a página.

FOURSQUARE_TIMEOUT_SEG = 6
FOURSQUARE_RAIO_M = 10000
FOURSQUARE_API_VERSION = "2025-06-17"

# Cada categoria pode usar mais de um termo de busca (em inglês, que é
# como a Foursquare guarda os nomes de categoria internamente) — igual à
# ideia dos filtros do Overpass, pra pegar mais variedade de resultado
# real (ex: "Atrações & Lazer" também busca shopping e praça).
FOURSQUARE_TERMOS_POR_TIPO = {
    "supermarket": ["supermarket", "grocery store"],
    "restaurant":  ["restaurant"],
    "pharmacy":    ["pharmacy", "drugstore", "farmácia", "drogaria"],
    "leisure":     ["tourist attraction", "shopping mall", "plaza", "park"],
}


def _buscar_foursquare_termo(api_key: str, termo: str, lat: float, lng: float) -> list[dict]:
    resp = requests.get(
        "https://places-api.foursquare.com/places/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Places-Api-Version": FOURSQUARE_API_VERSION,
            "Accept": "application/json",
        },
        params={
            "query": termo,
            "ll": f"{lat},{lng}",
            "radius": FOURSQUARE_RAIO_M,
            "sort": "DISTANCE",
            "limit": 10,
            "fields": "name,latitude,longitude,distance,rating,stats",
        },
        timeout=FOURSQUARE_TIMEOUT_SEG,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


@guia_publico_bp.route("/api/g/<slug>/locais-proximos")
def locais_proximos(slug):
    imovel = _buscar_imovel_publico(slug)
    api_key = current_app.config.get("FOURSQUARE_API_KEY", "")

    if not api_key:
        return jsonify({"foursquare_configurado": False, "locais": []})

    if not (imovel.lat and imovel.lng):
        return jsonify({"foursquare_configurado": True, "locais": []})

    tipo = request.args.get("tipo", "supermarket")
    termos = FOURSQUARE_TERMOS_POR_TIPO.get(tipo, FOURSQUARE_TERMOS_POR_TIPO["supermarket"])

    encontrados = {}
    try:
        # Dispara os termos da categoria em paralelo (em vez de um atrás do
        # outro) pra não somar o tempo de cada chamada — importante porque
        # "Atrações & Lazer" sozinha já usa 4 termos diferentes.
        with ThreadPoolExecutor(max_workers=len(termos)) as executor:
            futures = [
                executor.submit(_buscar_foursquare_termo, api_key, termo, imovel.lat, imovel.lng)
                for termo in termos
            ]
            for future in as_completed(futures):
                for lugar in future.result():
                    chave = lugar.get("fsq_place_id") or lugar.get("name")
                    if not chave or chave in encontrados:
                        continue
                    if lugar.get("latitude") is None or lugar.get("longitude") is None:
                        continue
                    stats = lugar.get("stats") or {}
                    rating = lugar.get("rating")
                    encontrados[chave] = {
                        "nome": lugar.get("name"),
                        "lat": lugar.get("latitude"),
                        "lng": lugar.get("longitude"),
                        "distancia_km": round((lugar.get("distance") or 0) / 1000, 2),
                        "rating": round(rating / 2, 1) if rating is not None else None,  # escala 0-10 -> 0-5 estrelas
                        "total_avaliacoes": stats.get("total_ratings"),
                    }
    except requests.RequestException:
        current_app.logger.exception("Falha ao consultar Foursquare Places API (guia do hóspede)")
        return jsonify({"foursquare_configurado": True, "locais": [], "erro": True})

    locais = sorted(encontrados.values(), key=lambda p: p["distancia_km"])[:5]
    return jsonify({"foursquare_configurado": True, "locais": locais})


# ── API pública do guia (JSON — usada pelo _criarPDF() no navegador) ─────────

@guia_publico_bp.route("/api/g/<slug>")
def guia_hospede_json(slug):
    imovel = _buscar_imovel_publico(slug)

    foto_url = f"/static/uploads/{imovel.foto_principal}" if imovel.foto_principal else None

    return jsonify({
        "titulo":   imovel.titulo,
        "endereco": imovel.endereco,
        "foto_url": foto_url,

        "lat": imovel.lat,
        "lng": imovel.lng,

        "wifi_rede":       imovel.wifi_rede       or "",
        "wifi_senha":      imovel.wifi_senha      or "",
        "senha_fechadura": imovel.senha_fechadura or "",

        "contato_telefone": imovel.contato_telefone or "",
        "contato_email":    imovel.contato_email    or "",

        "utensilios": _parse_utensilios(imovel.utensilios),
        "regras":     _parse_regras(imovel.regras),

        "checkin_padrao":      imovel.checkin_padrao      or "14:00",
        "checkout_padrao":     imovel.checkout_padrao     or "11:00",
        "capacidade_max":      imovel.capacidade_max,
        "qtd_quartos":         imovel.qtd_quartos,
        "qtd_banheiros":       imovel.qtd_banheiros,
        "qtd_camas":           imovel.qtd_camas,
        "diaria_base":         str(imovel.diaria_base or ""),
        "taxa_limpeza_padrao": str(imovel.taxa_limpeza_padrao or ""),

        "prazo_cancelamento_gratis": imovel.prazo_cancelamento_gratis,
        "multa_tipo":  imovel.multa_tipo  or "sem_multa",
        "multa_valor": str(imovel.multa_valor or ""),

        # DE PROPÓSITO NÃO INCLUÍDO:
        # - id sequencial do imóvel
        # - user_id / dono
        # - estadias, valores financeiros, nomes de hóspedes
        # - grupo (nome do grupo pode revelar organização interna do host)
    })