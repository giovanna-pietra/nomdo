"""
app/utils/helpers.py
Funções auxiliares genéricas.
"""

import random
from datetime import date, datetime

IDADE_MINIMA_CADASTRO = 13


def calcular_idade(data_nascimento) -> int:
    """
    Calcula idade em anos completos a partir de uma data de nascimento —
    aceita tanto um objeto date/datetime quanto uma string "AAAA-MM-DD"
    (formato usado nos formulários de cadastro/perfil).
    """
    if isinstance(data_nascimento, str):
        data_nascimento = datetime.strptime(data_nascimento, "%Y-%m-%d").date()
    elif isinstance(data_nascimento, datetime):
        data_nascimento = data_nascimento.date()

    hoje = date.today()
    idade = hoje.year - data_nascimento.year
    # Ainda não fez aniversário esse ano -> subtrai 1
    if (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day):
        idade -= 1
    return idade


def idade_minima_atingida(data_nascimento, minimo: int = IDADE_MINIMA_CADASTRO) -> bool:
    """
    True se a data de nascimento informada corresponde a alguém com pelo
    menos `minimo` anos (padrão 13, política mínima de cadastro do app —
    vale tanto pro cadastro manual quanto pra conclusão de perfil de quem
    entrou pelo Google). Data inválida/vazia é tratada como reprovada
    (quem chama já deve ter validado que o campo foi preenchido antes).
    """
    try:
        return calcular_idade(data_nascimento) >= minimo
    except (ValueError, TypeError, AttributeError):
        return False


def gerar_codigo(digitos: int = 6) -> str:
    """Gera código numérico aleatório para verificação."""
    lower = 10 ** (digitos - 1)
    upper = (10 ** digitos) - 1
    return str(random.randint(lower, upper))


def formatar_nome_exibicao(nome_completo: str) -> str:
    """
    Retorna 'Primeiro Último' se couber em 15 chars,
    senão apenas o primeiro nome.
    """
    if not nome_completo:
        return ""

    nomes = nome_completo.strip().split()

    if len(nomes) == 1:
        return nomes[0]

    primeiro = nomes[0]
    ultimo   = nomes[-1]
    nome_curto = f"{primeiro} {ultimo}"

    return nome_curto if len(nome_curto) <= 15 else primeiro
