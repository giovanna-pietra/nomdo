"""
app/routes/pg_rotinas.py
Página dedicada de Rotinas e Lembretes — parte do desmembramento do antigo
Hub do Anfitrião (Task de redesign do Hub): antes tudo vivia amontoado numa
página só, agora cada assunto tem a sua.

`LembreteConfig` é uma REGRA recorrente por imóvel (ex: "trocar pilha da
fechadura a cada 90 dias" ou "revisar o ar-condicionado a cada 6 meses") —
bem diferente das `HubTarefa` (que são os itens concretos/pontuais disparados
por essas regras, ou registrados na mão, e vivem nas páginas de Limpezas e
Manutenções). Aqui só mexemos com as regras — CRUD via
/api/hub/lembretes/* (já existentes em app/routes/hub.py), essa página só
lista e server-renderiza os campos computados (label/próxima data/vencido).
"""

from flask import Blueprint, redirect, request, url_for

from app.models import Imovel, LembreteConfig
from app.models.hub import TIPOS_LEMBRETE, TIPOS_EVENTO
from app.utils import login_required, get_effective_owner_id

rotinas_bp = Blueprint("rotinas", __name__)


def contexto_rotinas(owner_id, request_args=None):
    """Monta o dicionário de contexto usado pelo template/partial de Rotinas.

    `request_args` é opcional e aceita qualquer dict-like (ex.: Flask
    `request.args`) com os filtros `imovel_id` e `tipo`. Se omitido, lê
    `flask.request.args` diretamente — útil tanto para a rota própria
    (`/rotinas`) quanto para a rota do Hub, que pode chamar esta função
    para montar a aba "Rotinas" dentro de `hub_anfitriao()`.
    """
    if request_args is None:
        request_args = request.args

    lista_imoveis = Imovel.query.filter_by(user_id=owner_id).order_by(Imovel.titulo.asc()).all()
    imoveis_titulo = {im.id: im.titulo for im in lista_imoveis}

    query = LembreteConfig.query.filter_by(user_id=owner_id)

    raw_imovel_id = request_args.get("imovel_id")
    imovel_id = int(raw_imovel_id) if raw_imovel_id else None
    if imovel_id:
        query = query.filter(LembreteConfig.imovel_id == imovel_id)

    tipo = request_args.get("tipo")
    if tipo and tipo in TIPOS_LEMBRETE:
        query = query.filter(LembreteConfig.tipo == tipo)
    else:
        tipo = ""

    configs = query.order_by(LembreteConfig.created_at.desc()).all()

    # Monta os dados já processados (label/próxima data/vencido) usando os
    # métodos do próprio model — a página server-renderiza direto do banco,
    # sem precisar chamar /api/hub/lembretes de novo.
    rotinas = []
    for cfg in configs:
        meta = TIPOS_LEMBRETE.get(cfg.tipo, {"icone": "📌", "cor": "#7c3aed"})
        proxima = cfg.proxima_data()
        rotinas.append({
            "id": cfg.id,
            "tipo": cfg.tipo,
            "icone": meta.get("icone", "📌"),
            "cor": meta.get("cor", "#7c3aed"),
            "titulo": cfg.titulo or "",
            "label": cfg.label(),
            "descricao": cfg.descricao or "",
            "imovel_id": cfg.imovel_id,
            "imovel": imoveis_titulo.get(cfg.imovel_id, "—"),
            "intervalo_dias": cfg.intervalo_dias,
            "ativo": cfg.ativo,
            "por_evento": cfg.tipo in TIPOS_EVENTO,
            "proxima_data": proxima.strftime("%d/%m/%Y") if proxima else None,
            "dias_para_vencer": cfg.dias_para_vencer(),
            "vencido": cfg.vencido(),
        })

    # Vencidas primeiro; depois por menor "dias_para_vencer" (rotinas por
    # evento, sem data, ficam por último, na ordem original created_at desc).
    rotinas.sort(key=lambda r: (
        0 if r["vencido"] else 1,
        r["dias_para_vencer"] if r["dias_para_vencer"] is not None else 9999,
    ))

    return {
        "rotinas": rotinas,
        "imoveis": lista_imoveis,
        "tipos_lembrete": TIPOS_LEMBRETE,
        "tipos_evento": list(TIPOS_EVENTO),
        "filtro_imovel_id": imovel_id,
        "filtro_tipo": tipo,
    }


@rotinas_bp.route("/rotinas")
@login_required
def pagina():
    # Página própria descontinuada — Rotinas e Lembretes agora vive como aba
    # dentro do Hub do Anfitrião. Mantemos a rota só para não quebrar
    # favoritos/links antigos.
    return redirect(url_for("main.hub_anfitriao", tab="rotinas"))
