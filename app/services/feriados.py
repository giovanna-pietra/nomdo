"""
app/services/feriados.py
Calendário de feriados nacionais brasileiros — fixos e móveis — calculado
matematicamente (sem depender de API externa nem de atualização manual
ano a ano).

Usado pelo motor de precificação do Hub (app/services/precificacao.py)
para sugerir aumento de preço em datas de alta demanda.
"""

from __future__ import annotations

from datetime import date, timedelta


# ── Feriados fixos (mês, dia, nome) ───────────────────────────────────────────
FERIADOS_FIXOS = [
    (1, 1,   "Ano Novo"),
    (4, 21,  "Tiradentes"),
    (5, 1,   "Dia do Trabalho"),
    (9, 7,   "Independência do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2,  "Finados"),
    (11, 15, "Proclamação da República"),
    (12, 25, "Natal"),
    (12, 31, "Réveillon"),
]


def _pascoa(ano: int) -> date:
    """
    Data da Páscoa para o ano informado — algoritmo de Gauss/Anonymous
    Gregorian (padrão, sem dependências externas).
    """
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_moveis(ano: int) -> list[tuple[date, str]]:
    """Feriados calculados a partir da Páscoa daquele ano."""
    pascoa = _pascoa(ano)
    return [
        (pascoa - timedelta(days=47), "Carnaval"),
        (pascoa - timedelta(days=46), "Quarta-feira de Cinzas"),
        (pascoa - timedelta(days=2),  "Paixão de Cristo"),
        (pascoa,                      "Páscoa"),
        (pascoa + timedelta(days=60), "Corpus Christi"),
    ]


def feriados_do_ano(ano: int) -> dict[date, str]:
    """Todos os feriados nacionais (fixos + móveis) de um ano, {data: nome}."""
    feriados: dict[date, str] = {}
    for mes, dia, nome in FERIADOS_FIXOS:
        feriados[date(ano, mes, dia)] = nome
    for data_ev, nome in feriados_moveis(ano):
        feriados[data_ev] = nome
    return feriados


def eh_prolongado(data_feriado: date) -> bool:
    """
    Considera "feriado prolongado" quando o feriado cai numa
    quinta/sexta/segunda/terça — criando um fim de semana estendido de
    alta demanda para hospedagem.
    """
    return data_feriado.weekday() in (0, 1, 3, 4)  # seg, ter, qui, sex


def proximos_feriados(hoje: date | None = None, dias_janela: int = 365) -> list[dict]:
    """
    Lista os feriados nacionais entre `hoje` e `hoje + dias_janela`,
    cobrindo virada de ano quando a janela cruza dezembro/janeiro.

    Retorna dicts: {"data": date, "nome": str, "prolongado": bool, "dias_restantes": int}
    """
    hoje = hoje or date.today()
    limite = hoje + timedelta(days=dias_janela)

    anos = {hoje.year, limite.year}
    todos: dict[date, str] = {}
    for ano in anos:
        todos.update(feriados_do_ano(ano))

    resultado = []
    for data_ev, nome in todos.items():
        if hoje <= data_ev <= limite:
            resultado.append({
                "data": data_ev,
                "nome": nome,
                "prolongado": eh_prolongado(data_ev),
                "dias_restantes": (data_ev - hoje).days,
            })

    resultado.sort(key=lambda x: x["data"])
    return resultado


# ── Datas comerciais (aumentam a procura por temporada em qualquer região) ────
# Não são feriado, mas historicamente elevam a demanda por aluguel de
# temporada (viagem em família, presente, fim de semana fora) — aparecem nas
# oportunidades de precificação mesmo sem o anfitrião cadastrar nada.

def _nth_weekday_do_mes(ano: int, mes: int, weekday: int, n: int) -> date:
    """
    Encontra a n-ésima ocorrência de um dia da semana num mês (ex: "2º
    domingo de maio", "4ª sexta-feira de novembro"). `weekday` segue o
    padrão de date.weekday() (0=segunda ... 6=domingo).
    """
    d = date(ano, mes, 1)
    primeiro_weekday = d.weekday()
    delta_ate_primeiro = (weekday - primeiro_weekday) % 7
    dia = 1 + delta_ate_primeiro + (n - 1) * 7
    return date(ano, mes, dia)


def _ultimo_weekday_do_mes(ano: int, mes: int, weekday: int) -> date:
    """Última ocorrência de um dia da semana num mês (ex: Black Friday)."""
    if mes == 12:
        ultimo_dia = date(ano, 12, 31)
    else:
        ultimo_dia = date(ano, mes + 1, 1) - timedelta(days=1)
    delta = (ultimo_dia.weekday() - weekday) % 7
    return ultimo_dia - timedelta(days=delta)


def datas_comerciais_do_ano(ano: int) -> dict[date, str]:
    """Datas comerciais fortes daquele ano, {data: nome}."""
    return {
        _nth_weekday_do_mes(ano, 5, 6, 2):    "Dia das Mães",
        date(ano, 6, 12):                     "Dia dos Namorados",
        _nth_weekday_do_mes(ano, 8, 6, 2):    "Dia dos Pais",
        _ultimo_weekday_do_mes(ano, 11, 4):   "Black Friday",
    }


def proximas_datas_comerciais(hoje: date | None = None, dias_janela: int = 365) -> list[dict]:
    """
    Mesmo formato de `proximos_feriados`, mas para datas comerciais (Dia das
    Mães, Namorados, Pais, Black Friday) — sempre `prolongado=False`
    (não é feriado, então não tem lógica de fim de semana estendido).
    """
    hoje = hoje or date.today()
    limite = hoje + timedelta(days=dias_janela)

    anos = {hoje.year, limite.year}
    todos: dict[date, str] = {}
    for ano in anos:
        todos.update(datas_comerciais_do_ano(ano))

    resultado = []
    for data_ev, nome in todos.items():
        if hoje <= data_ev <= limite:
            resultado.append({
                "data": data_ev,
                "nome": nome,
                "prolongado": False,
                "dias_restantes": (data_ev - hoje).days,
            })

    resultado.sort(key=lambda x: x["data"])
    return resultado


# ── Feriados estaduais / pontos facultativos ──────────────────────────────────
# Cobertura curada dos estados com data(s) estadual(is) mais conhecida(s) e
# consolidada(s) em lei — não é uma lista exaustiva de todo feriado municipal
# do Brasil (são milhares e variam por prefeitura), só o nível estadual, que
# dá pra manter num dict simples sem precisar de API externa.
FERIADOS_ESTADUAIS: dict[str, list[tuple[int, int, str]]] = {
    "AC": [(1, 23, "Dia da Amazônia (Tratado de Petrópolis)")],
    "AL": [(9, 16, "Emancipação Política de Alagoas")],
    "AM": [(9, 5,  "Elevação do Amazonas à categoria de província")],
    "BA": [(7, 2,  "Independência da Bahia")],
    "CE": [(3, 25, "Abolição da escravidão no Ceará")],
    "DF": [(4, 21, "Fundação de Brasília"), (11, 30, "Dia do Evangélico")],
    "ES": [(10, 28, "Dia do Servidor Público")],
    "MA": [(7, 28, "Adesão do Maranhão à independência do Brasil")],
    "MT": [(11, 20, "Consciência Negra (Mato Grosso)")],
    "PA": [(8, 15, "Adesão do Grão-Pará à independência do Brasil")],
    "PB": [(8, 5,  "Fundação do Estado da Paraíba")],
    "PE": [(3, 6,  "Revolução Pernambucana / Data Magna")],
    "PI": [(10, 19, "Dia do Piauí")],
    "RJ": [(4, 23, "Dia de São Jorge"), (11, 20, "Consciência Negra (Rio de Janeiro)")],
    "RN": [(11, 20, "Consciência Negra (Rio Grande do Norte)")],
    "RS": [(9, 20, "Revolução Farroupilha")],
    "SC": [(8, 11, "Criação da Capitania de Santa Catarina")],
    "SE": [(7, 8,  "Emancipação Política de Sergipe")],
    "SP": [(7, 9,  "Revolução Constitucionalista de 1932")],
}


def proximos_feriados_estaduais(estado: str | None, hoje: date | None = None, dias_janela: int = 365) -> list[dict]:
    """
    Feriados estaduais do UF informado dentro da janela — mesmo formato de
    `proximos_feriados`. Retorna lista vazia se o estado não for reconhecido
    ou não tiver data estadual cadastrada.
    """
    if not estado:
        return []
    lista = FERIADOS_ESTADUAIS.get(estado.strip().upper())
    if not lista:
        return []

    hoje = hoje or date.today()
    limite = hoje + timedelta(days=dias_janela)

    anos = {hoje.year, limite.year}
    todos: dict[date, str] = {}
    for ano in anos:
        for mes, dia, nome in lista:
            todos[date(ano, mes, dia)] = nome

    resultado = []
    for data_ev, nome in todos.items():
        if hoje <= data_ev <= limite:
            resultado.append({
                "data": data_ev,
                "nome": nome,
                "prolongado": eh_prolongado(data_ev),
                "dias_restantes": (data_ev - hoje).days,
            })

    resultado.sort(key=lambda x: x["data"])
    return resultado
