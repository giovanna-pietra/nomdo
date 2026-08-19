"""
app/services/planos.py
Regra única de negócio dos planos de assinatura — quem quiser saber
"quanto custa" ou "até quantos imóveis cada plano cobre" consulta este
módulo, nunca reimplementa a faixa em outro lugar.

Faixas (por quantidade de imóveis do Proprietário — ver User.owner_id):
    ate_5    -> até 5 imóveis
    ate_10   -> até 10 imóveis
    mais_10  -> 11 imóveis ou mais

Os preços vêm de config (PLANO_ATE_5_CENTS / PLANO_ATE_10_CENTS /
PLANO_MAIS_10_CENTS em config/settings.py), não são fixos aqui, pra
dar pra ajustar via .env sem alterar código.
"""
from __future__ import annotations

from flask import current_app

# Ordem sempre do menor pro maior — usada tanto pra decidir o plano de
# alguém quanto pra desenhar os 3 cards de preço na tela de pagamento.
PLANOS = {
    "ate_5":   {"limite": 5,    "config_key": "PLANO_ATE_5_CENTS"},
    "ate_10":  {"limite": 10,   "config_key": "PLANO_ATE_10_CENTS"},
    "mais_10": {"limite": None, "config_key": "PLANO_MAIS_10_CENTS"},  # sem teto
}

ORDEM_PLANOS = ("ate_5", "ate_10", "mais_10")


def calcular_plano(qtd_imoveis: int) -> str:
    """Dado o nº de imóveis do Proprietário, devolve a chave do menor
    plano que cobre essa quantidade."""
    qtd_imoveis = qtd_imoveis or 0
    for chave in ORDEM_PLANOS:
        limite = PLANOS[chave]["limite"]
        if limite is None or qtd_imoveis <= limite:
            return chave
    return ORDEM_PLANOS[-1]


def limite_do_plano(plano: str) -> int | None:
    """None significa sem teto (plano mais_10)."""
    return PLANOS.get(plano, PLANOS["mais_10"])["limite"]


def plano_cobre(qtd_imoveis: int, plano: str) -> bool:
    """True se o plano informado ainda cobre essa quantidade de imóveis
    (usado pra decidir se bloqueia o cadastro de um novo imóvel)."""
    limite = limite_do_plano(plano)
    if limite is None:
        return True
    return (qtd_imoveis or 0) <= limite


def valor_cents_do_plano(plano: str) -> int:
    """Lê o preço atual do plano (em centavos) direto da config —
    precisa estar dentro de um contexto de aplicação Flask."""
    info = PLANOS.get(plano) or PLANOS["ate_5"]
    return int(current_app.config.get(info["config_key"], 0) or 0)


def listar_planos() -> list[dict]:
    """Monta a lista ordenada [{"chave", "limite", "valor_cents"}, ...]
    pronta pra desenhar os cards de preço em pagamento.html."""
    return [
        {
            "chave": chave,
            "limite": PLANOS[chave]["limite"],
            "valor_cents": valor_cents_do_plano(chave),
        }
        for chave in ORDEM_PLANOS
    ]


def plano_recomendado(qtd_imoveis: int) -> str:
    """Mesma regra de calcular_plano — nome mais explícito pra uso na
    tela de pagamento, onde queremos destacar um card como
    'recomendado pra você' de acordo com os imóveis já cadastrados."""
    return calcular_plano(qtd_imoveis)
