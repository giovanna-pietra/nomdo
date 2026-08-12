"""
app/services/asaas_service.py
Integração com a Asaas. Cobre: criar/reaproveitar o cliente na Asaas,
gerar uma assinatura mensal recorrente (modelo atual de acesso ao
sistema — ver app/models/assinatura.py e app/services/planos.py) e,
por compatibilidade, ainda sabe gerar uma cobrança avulsa isolada.

Pré-pronto: sem ASAAS_API_KEY configurada nenhuma chamada é feita de
verdade — as funções levantam AsaasNaoConfigurado, que as rotas tratam
mostrando uma mensagem amigável em vez de quebrar. Quando a chave real
existir, basta preencher ASAAS_API_KEY (e opcionalmente ASAAS_ENV) no
.env — nenhum código precisa mudar.

Docs: https://docs.asaas.com/reference/comece-por-aqui (URLs base)
      https://docs.asaas.com/reference/criar-novo-cliente
      https://docs.asaas.com/reference/criar-nova-assinatura
      https://docs.asaas.com/reference/atualizar-uma-assinatura-existente
      https://docs.asaas.com/reference/remover-uma-assinatura
"""
from __future__ import annotations

import requests
from flask import current_app

# NOTA: a base de sandbox é "api-sandbox.asaas.com/v3" (com hífen antes
# de "sandbox"), não "sandbox.asaas.com/api/v3" — confirmado na doc
# oficial. Usar a URL errada faz toda chamada em ambiente de teste
# falhar com erro de conexão/DNS.
BASE_URL_SANDBOX    = "https://api-sandbox.asaas.com/v3"
BASE_URL_PRODUCTION = "https://api.asaas.com/v3"


class AsaasNaoConfigurado(Exception):
    """Levantada quando ASAAS_API_KEY ainda não foi preenchida."""


class AsaasErro(Exception):
    """Levantada quando a API da Asaas responde com erro."""


def _base_url() -> str:
    ambiente = (current_app.config.get("ASAAS_ENV") or "sandbox").strip().lower()
    return BASE_URL_PRODUCTION if ambiente == "production" else BASE_URL_SANDBOX


def _headers() -> dict:
    api_key = (current_app.config.get("ASAAS_API_KEY") or "").strip()
    if not api_key:
        raise AsaasNaoConfigurado(
            "ASAAS_API_KEY não configurada. Preencha no .env para ativar o paywall."
        )
    return {
        "access_token": api_key,
        "Content-Type": "application/json",
        "User-Agent": "Nomdo",
    }


def _request(metodo: str, caminho: str, **kwargs):
    url = f"{_base_url()}{caminho}"
    resposta = requests.request(metodo, url, headers=_headers(), timeout=15, **kwargs)

    try:
        dados = resposta.json()
    except ValueError:
        dados = {}

    if resposta.status_code >= 400:
        mensagens = [e.get("description", "") for e in dados.get("errors", [])] or [resposta.text]
        raise AsaasErro("; ".join(m for m in mensagens if m) or "Erro desconhecido na Asaas")

    return dados


def criar_ou_obter_cliente(user) -> str:
    """
    Retorna o asaas_customer_id do usuário, criando na Asaas se ainda
    não existir (e salvando o id em user.asaas_customer_id).
    """
    if user.asaas_customer_id:
        return user.asaas_customer_id

    payload = {
        "name": user.nome,
        "email": user.email,
    }
    if user.cpf:
        payload["cpfCnpj"] = "".join(ch for ch in user.cpf if ch.isdigit())
    if user.telefone:
        payload["mobilePhone"] = "".join(ch for ch in user.telefone if ch.isdigit())

    dados = _request("POST", "/customers", json=payload)

    customer_id = dados.get("id")
    if not customer_id:
        raise AsaasErro("Asaas não retornou um id de cliente.")

    user.asaas_customer_id = customer_id
    return customer_id


def criar_cobranca_acesso(user, valor_cents: int, billing_type: str = "UNDEFINED") -> dict:
    """
    Cria uma cobrança única (pagamento avulso, não assinatura) referente
    à liberação de acesso ao sistema. `billing_type` pode ser BOLETO,
    PIX, CREDIT_CARD ou UNDEFINED (a Asaas mostra uma tela de checkout
    com todas as opções disponíveis).

    Retorna o dict cru da resposta da Asaas (contém "id" e "invoiceUrl").
    """
    from datetime import date, timedelta

    customer_id = criar_ou_obter_cliente(user)

    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": round(valor_cents / 100, 2),
        "dueDate": (date.today() + timedelta(days=3)).isoformat(),
        "description": "Nomdo — acesso único ao sistema",
    }

    return _request("POST", "/payments", json=payload)


def consultar_cobranca(asaas_payment_id: str) -> dict:
    """Consulta o status atual de uma cobrança direto na Asaas (útil para
    reconciliar caso um webhook não chegue)."""
    return _request("GET", f"/payments/{asaas_payment_id}")


# ─────────────────────────────────────────────────────────────────────
# Assinaturas (modelo atual — pagamento mensal recorrente)
# ─────────────────────────────────────────────────────────────────────

def criar_assinatura(
    user,
    valor_cents: int,
    ciclo: str = "MONTHLY",
    billing_type: str = "UNDEFINED",
    descricao: str = "Nomdo — assinatura mensal",
) -> dict:
    """
    Cria uma assinatura recorrente na Asaas pro Proprietário informado
    (nunca chamar com um Anfitrião-ajudante — quem assina é sempre a
    conta dona, ver User.owner_id). A Asaas passa a gerar uma cobrança
    (Payment) automaticamente a cada ciclo.

    Retorna o dict cru da resposta da Asaas (contém "id" no formato
    "sub_xxx" e "nextDueDate", entre outros campos).
    """
    from datetime import date, timedelta

    customer_id = criar_ou_obter_cliente(user)

    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": round(valor_cents / 100, 2),
        "nextDueDate": (date.today() + timedelta(days=3)).isoformat(),
        "cycle": ciclo,
        "description": descricao,
    }

    return _request("POST", "/subscriptions", json=payload)


def atualizar_valor_assinatura(
    asaas_subscription_id: str,
    valor_cents: int,
    atualizar_cobrancas_pendentes: bool = False,
) -> dict:
    """
    Atualiza o valor de uma assinatura já existente na Asaas — usado
    quando o Proprietário muda de plano (troca de faixa de imóveis).

    `atualizar_cobrancas_pendentes=True` (updatePendingPayments na Asaas)
    também reajusta cobranças já geradas que ainda estão em aberto; sem
    isso, só as próximas cobranças do novo ciclo saem com o valor novo.
    """
    payload = {
        "value": round(valor_cents / 100, 2),
        "updatePendingPayments": atualizar_cobrancas_pendentes,
    }
    return _request("PUT", f"/subscriptions/{asaas_subscription_id}", json=payload)


def cancelar_assinatura(asaas_subscription_id: str) -> dict:
    """Cancela (remove) uma assinatura na Asaas — não gera mais cobranças
    futuras; cobranças já emitidas continuam existindo normalmente."""
    return _request("DELETE", f"/subscriptions/{asaas_subscription_id}")


def consultar_assinatura(asaas_subscription_id: str) -> dict:
    """Consulta o status atual de uma assinatura direto na Asaas (útil
    para reconciliar caso um webhook não chegue)."""
    return _request("GET", f"/subscriptions/{asaas_subscription_id}")


def obter_primeira_cobranca_assinatura(asaas_subscription_id: str) -> dict | None:
    """
    Uma assinatura recém-criada na Asaas não devolve um link de checkout
    diretamente — o link (invoiceUrl) mora na primeira cobrança (Payment)
    que a Asaas gera automaticamente para ela. Busca essa cobrança pra
    redirecionar o usuário pro checkout logo após criar a assinatura.

    Retorna o dict cru da primeira cobrança encontrada, ou None se a
    Asaas ainda não tiver gerado nenhuma (raro, mas possível levar
    alguns instantes).
    """
    dados = _request("GET", "/payments", params={"subscription": asaas_subscription_id})
    cobrancas = dados.get("data") or []
    return cobrancas[0] if cobrancas else None
