"""
app/utils/currency.py
Formatação de valores monetários de acordo com a preferência de moeda
salva no perfil do usuário (User.currency: BRL/USD/EUR).

Não faz conversão de taxa de câmbio — só troca símbolo e o estilo de
separador de milhar/decimal apropriado pra cada moeda. O valor numérico
salvo no banco continua o mesmo.
"""

CURRENCY_SYMBOLS = {
    "BRL": "R$",
    "USD": "$",
    "EUR": "€",
}

# Moedas cujo estilo de número é "1,234.56" (ponto decimal, vírgula milhar).
# As demais (BRL, EUR) usam "1.234,56" (vírgula decimal, ponto milhar).
_ESTILO_PONTO_DECIMAL = {"USD"}


def moeda_symbol(currency):
    """Retorna o símbolo da moeda (R$, $, €), com BRL como padrão."""
    currency = (currency or "BRL").upper()
    return CURRENCY_SYMBOLS.get(currency, CURRENCY_SYMBOLS["BRL"])


def formatar_moeda(valor, currency=None):
    """
    Formata um número como string monetária de acordo com a moeda
    informada. Ex: formatar_moeda(1234.5, 'USD') -> '$ 1,234.50'
                   formatar_moeda(1234.5, 'BRL') -> 'R$ 1.234,50'
    """
    try:
        valor = float(valor or 0)
    except (TypeError, ValueError):
        valor = 0.0

    currency = (currency or "BRL").upper()
    simbolo = moeda_symbol(currency)

    texto = "{:,.2f}".format(valor)  # formato padrão Python: 1,234.56

    if currency not in _ESTILO_PONTO_DECIMAL:
        # Troca milhar <-> decimal usando um placeholder, pra virar o
        # estilo BRL/EUR: 1.234,56
        texto = texto.replace(",", "§").replace(".", ",").replace("§", ".")

    return "{} {}".format(simbolo, texto)
