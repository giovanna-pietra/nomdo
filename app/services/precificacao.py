"""
app/services/precificacao.py
Motor de sugestões de precificação do Hub do Anfitrião.

Combina:
  1. Feriados nacionais (fixos + móveis), calculados automaticamente
     em app/services/feriados.py.
  2. Feriados estaduais (quando o imóvel tem estado cadastrado).
  3. Datas comerciais fortes (Dia das Mães/Namorados/Pais, Black Friday) —
     também automáticas, sem precisar de cadastro.
  4. Eventos personalizados cadastrados pelo anfitrião (EventoPrecificacao)
     — show, festival, temporada local, réveillon regional etc.

Imóveis que ficam na mesma cidade (campo Imovel.cidade) são agrupados numa
única "região": cada oportunidade nacional/estadual/comercial aparece 1 vez
por região (não 1 vez por imóvel), listando quais imóveis ela afeta — assim
o anfitrião com vários imóveis na mesma cidade não vê o mesmo feriado
repetido várias vezes. Imóvel sem cidade cadastrada não agrupa com nenhum
outro (mantém o comportamento antigo: 1 linha por imóvel).

Para cada região, dentro de uma janela de dias a partir de hoje, gera uma
lista de "dicas" com a data, o motivo e o percentual de aumento sugerido
(configurável por nível de impacto em User.pct_precificacao_*).

Não é um motor de disparo de e-mail — é só leitura/cálculo, consumido pela
rota /api/hub/dados para renderizar o card "Oportunidades de Precificação".
"""

from __future__ import annotations

from datetime import date

from app.models import Imovel, EventoPrecificacao
from app.models.precificacao import PCT_PADRAO, NIVEIS_IMPACTO
from app.services.feriados import (
    proximos_feriados,
    proximos_feriados_estaduais,
    proximas_datas_comerciais,
)

DIAS_JANELA_PADRAO = 365

_ICONES_TIPO = {
    "feriado":   "fa-calendar-days",
    "estadual":  "fa-flag",
    "comercial": "fa-tags",
    "evento":    "fa-tag",
}


def _icone_tipo(tipo: str) -> str:
    return _ICONES_TIPO.get(tipo, "fa-calendar-days")


def _agrupar_imoveis_por_regiao(imoveis: list[Imovel]) -> dict:
    """
    Agrupa imóveis que ficam na mesma cidade — pra que feriados/datas
    comerciais nacionais não se repitam uma vez por imóvel quando vários
    imóveis do anfitrião ficam na mesma região. Imóvel sem cidade cadastrada
    vira seu próprio grupo isolado (comportamento antigo: 1 linha por
    imóvel), já que não dá pra saber se ele compartilha região com outro.
    """
    grupos: dict = {}
    for im in imoveis:
        cidade = (im.cidade or "").strip()
        estado = (im.estado or "").strip().upper() or None
        if cidade:
            key = cidade.lower()
            label = cidade
        else:
            key = f"__sem_regiao_{im.id}__"
            label = None
        if key not in grupos:
            grupos[key] = {"label": label, "estado": estado, "imoveis": []}
        grupos[key]["imoveis"].append(im)
        if not grupos[key]["estado"] and estado:
            grupos[key]["estado"] = estado
    return grupos


def _percentuais_do_usuario(user) -> dict:
    # Antes lia User.pct_precificacao_alta/media/baixa, que o anfitrião podia
    # customizar no card "Percentuais de Aumento Sugerido" — esse card foi
    # removido da aba Precificação, então agora sempre usa os valores fixos
    # (alta 30%, média 15%, baixa 5%), sem depender de nenhum valor salvo
    # antigo que possa ter ficado diferente do padrão.
    return dict(PCT_PADRAO)


def _eventos_recorrentes_projetados(eventos: list[EventoPrecificacao], hoje: date, limite: date) -> list[dict]:
    """
    Para eventos marcados como recorrentes, projeta a data (dia/mês) para
    o ano atual e o ano seguinte, cobrindo virada de ano dentro da janela.
    Eventos não recorrentes só valem na data exata cadastrada.
    """
    projetados = []
    for ev in eventos:
        if ev.recorrente:
            for ano in {hoje.year, limite.year}:
                try:
                    data_projetada = ev.data.replace(year=ano)
                except ValueError:
                    # 29/fev em ano não bissexto — ignora essa projeção
                    continue
                if hoje <= data_projetada <= limite:
                    projetados.append({"evento": ev, "data": data_projetada})
        else:
            if hoje <= ev.data <= limite:
                projetados.append({"evento": ev, "data": ev.data})
    return projetados


def calcular_oportunidades(user, dias_janela: int = DIAS_JANELA_PADRAO) -> list[dict]:
    """
    Retorna a lista de oportunidades de precificação para todos os imóveis
    do anfitrião, ordenada por data. Cada item:

    {
        "imovel_id": int, "imovel_titulo": str, "imoveis": list[str],
        "regiao": str | None,
        "data": date, "data_fmt": "dd/mm/yyyy",
        "titulo": str, "tipo": "feriado" | "estadual" | "comercial" | "evento",
        "icone": str (classe fa-solid),
        "nivel_impacto": "alta" | "media" | "baixa",
        "percentual_sugerido": int,
        "dias_restantes": int, "prolongado": bool,
    }

    "imovel_id"/"imovel_titulo" continuam presentes (compat com quem só lia
    esses dois campos antes) e sempre apontam pro primeiro imóvel do grupo;
    "imoveis" tem a lista completa de imóveis afetados por aquela linha.
    """
    from datetime import timedelta

    hoje = date.today()
    limite = hoje + timedelta(days=dias_janela)

    imoveis = Imovel.query.filter_by(user_id=user.id).all()
    if not imoveis:
        return []

    pct = _percentuais_do_usuario(user)

    feriados = proximos_feriados(hoje, dias_janela)
    comerciais = proximas_datas_comerciais(hoje, dias_janela)

    eventos_todos = EventoPrecificacao.query.filter_by(user_id=user.id).all()
    eventos_gerais = [e for e in eventos_todos if e.imovel_id is None]
    eventos_por_imovel: dict[int, list[EventoPrecificacao]] = {}
    for e in eventos_todos:
        if e.imovel_id is not None:
            eventos_por_imovel.setdefault(e.imovel_id, []).append(e)

    grupos = _agrupar_imoveis_por_regiao(imoveis)

    oportunidades = []

    for grupo in grupos.values():
        titulos = [im.titulo for im in grupo["imoveis"]]
        primeiro = grupo["imoveis"][0]

        # ── Feriados nacionais (1x por região) ──────────────────────
        for f in feriados:
            nivel = "alta" if f["prolongado"] or f["nome"] in ("Réveillon", "Carnaval", "Natal") else "media"
            oportunidades.append({
                "imovel_id": primeiro.id, "imovel_titulo": primeiro.titulo,
                "imoveis": titulos, "regiao": grupo["label"],
                "data": f["data"],
                "data_fmt": f["data"].strftime("%d/%m/%Y"),
                "titulo": f["nome"] + (" (feriado prolongado)" if f["prolongado"] else ""),
                "tipo": "feriado", "icone": _icone_tipo("feriado"),
                "nivel_impacto": nivel,
                "percentual_sugerido": pct[nivel],
                "dias_restantes": f["dias_restantes"],
                "prolongado": f["prolongado"],
            })

        # ── Feriados estaduais (1x por região, só se o grupo tem UF) ─
        for f in proximos_feriados_estaduais(grupo["estado"], hoje, dias_janela):
            nivel = "alta" if f["prolongado"] else "media"
            oportunidades.append({
                "imovel_id": primeiro.id, "imovel_titulo": primeiro.titulo,
                "imoveis": titulos, "regiao": grupo["label"],
                "data": f["data"],
                "data_fmt": f["data"].strftime("%d/%m/%Y"),
                "titulo": f"{f['nome']} (feriado estadual — {grupo['estado']})",
                "tipo": "estadual", "icone": _icone_tipo("estadual"),
                "nivel_impacto": nivel,
                "percentual_sugerido": pct[nivel],
                "dias_restantes": f["dias_restantes"],
                "prolongado": f["prolongado"],
            })

        # ── Datas comerciais fortes (1x por região) ──────────────────
        for c in comerciais:
            nivel = "media"
            oportunidades.append({
                "imovel_id": primeiro.id, "imovel_titulo": primeiro.titulo,
                "imoveis": titulos, "regiao": grupo["label"],
                "data": c["data"],
                "data_fmt": c["data"].strftime("%d/%m/%Y"),
                "titulo": c["nome"],
                "tipo": "comercial", "icone": _icone_tipo("comercial"),
                "nivel_impacto": nivel,
                "percentual_sugerido": pct[nivel],
                "dias_restantes": c["dias_restantes"],
                "prolongado": False,
            })

        # ── Eventos cadastrados gerais — aplicam a todos os imóveis,
        #    1x por região (antes repetiam 1x por imóvel também) ─────
        for proj in _eventos_recorrentes_projetados(eventos_gerais, hoje, limite):
            ev = proj["evento"]
            data_ev = proj["data"]
            nivel = ev.nivel_impacto if ev.nivel_impacto in NIVEIS_IMPACTO else "media"
            oportunidades.append({
                "imovel_id": primeiro.id, "imovel_titulo": primeiro.titulo,
                "imoveis": titulos, "regiao": grupo["label"],
                "data": data_ev,
                "data_fmt": data_ev.strftime("%d/%m/%Y"),
                "titulo": ev.titulo,
                "tipo": "evento", "icone": _icone_tipo("evento"),
                "nivel_impacto": nivel,
                "percentual_sugerido": pct[nivel],
                "dias_restantes": (data_ev - hoje).days,
                "prolongado": False,
                "evento_id": ev.id,
            })

    # ── Eventos cadastrados específicos de um imóvel — continuam
    #    individuais (só fazem sentido pra aquele imóvel) ────────────
    for im in imoveis:
        evs = eventos_por_imovel.get(im.id, [])
        for proj in _eventos_recorrentes_projetados(evs, hoje, limite):
            ev = proj["evento"]
            data_ev = proj["data"]
            nivel = ev.nivel_impacto if ev.nivel_impacto in NIVEIS_IMPACTO else "media"
            oportunidades.append({
                "imovel_id": im.id, "imovel_titulo": im.titulo,
                "imoveis": [im.titulo], "regiao": None,
                "data": data_ev,
                "data_fmt": data_ev.strftime("%d/%m/%Y"),
                "titulo": ev.titulo,
                "tipo": "evento", "icone": _icone_tipo("evento"),
                "nivel_impacto": nivel,
                "percentual_sugerido": pct[nivel],
                "dias_restantes": (data_ev - hoje).days,
                "prolongado": False,
                "evento_id": ev.id,
            })

    oportunidades.sort(key=lambda o: (o["data"], -o["percentual_sugerido"]))
    return oportunidades
