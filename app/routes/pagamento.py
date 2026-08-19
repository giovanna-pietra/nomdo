"""
app/routes/pagamento.py
Paywall — assinatura mensal recorrente via Asaas, por faixa de
quantidade de imóveis (ver app/services/planos.py):
    até 5 imóveis   -> R$ 20/mês  ("ate_5")
    até 10 imóveis  -> R$ 35/mês  ("ate_10")
    11+ imóveis     -> R$ 50/mês  ("mais_10")

Donos/admins nunca passam por aqui: o gate global (app/__init__.py) já
libera quem é is_admin antes de chegar numa rota protegida. Um
Anfitrião-ajudante também nunca assina — quem paga é sempre a conta
Proprietária a que ele está vinculado (User.owner_id).

Fluxo:
  1) Usuário sem acesso é redirecionado pra /pagamento (gate global).
  2) Ele escolhe um plano -> POST /pagamento/checkout:
     - se ainda não tem assinatura na Asaas, cria uma nova
       (asaas_service.criar_assinatura) e redireciona pro checkout da
       primeira cobrança gerada;
     - se já tem assinatura ativa e só está trocando de plano, atualiza
       o valor na Asaas (asaas_service.atualizar_valor_assinatura) sem
       precisar de um novo checkout.
  3) A Asaas notifica confirmação/mudança via POST /webhooks/asaas
     (eventos SUBSCRIPTION_* e PAYMENT_*), que mantém Assinatura e
     User.pagamento_ativo sincronizados.

Enquanto ASAAS_API_KEY não estiver configurada, /pagamento/checkout
mostra um aviso amigável em vez de tentar chamar a API (ver
AsaasNaoConfigurado em asaas_service.py) — e o gate global nem chega a
bloquear ninguém, porque PAYWALL_ATIVO só liga de verdade com a chave
preenchida.
"""
from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint, current_app, flash, jsonify, redirect,
    render_template, request, session, url_for,
)

from app.extensions import db, csrf
from app.models import Assinatura, Imovel, Pagamento, User
from app.services import asaas_service, planos
from app.utils import login_required
from app.utils.i18n import t_flash

pagamento_bp = Blueprint("pagamento", __name__)


def _qtd_imoveis(owner_id: int) -> int:
    return Imovel.query.filter_by(user_id=owner_id).count()


def _assinatura_atual(user_id: int):
    return (
        Assinatura.query.filter_by(user_id=user_id)
        .order_by(Assinatura.id.desc())
        .first()
    )


@pagamento_bp.route("/pagamento")
@login_required
def pagina_pagamento():
    user = db.session.get(User, session.get("user_id"))
    if not user:
        return redirect(url_for("auth.login"))

    if user.is_admin:
        return redirect(url_for("reservas.dashboard"))

    # Diferente do antigo pagamento único ("pra sempre"), quem já tem
    # assinatura ativa continua podendo abrir esta página — é aqui que
    # ele vê o plano atual e troca de faixa se o nº de imóveis mudar.
    # Só o gate global (app/__init__.py) é que bloqueia quem NÃO tem
    # pagamento_ativo de navegar pro resto do sistema; esta rota em si
    # nunca bloqueia ninguém.

    # Um Anfitrião-ajudante não gerencia cobrança — quem paga é sempre a
    # conta Proprietária a que ele está vinculado. Em vez de deixá-lo
    # tentar assinar por uma conta que não é a dele, mostramos um aviso
    # explicando quem é responsável pelo acesso.
    if user.e_ajudante:
        dono = db.session.get(User, user.proprietario_id)
        return render_template(
            "pagamento.html",
            user=user,
            bloqueado_ajudante=True,
            dono=dono,
            planos=[],
            plano_recomendado=None,
            assinatura_atual=None,
            asaas_configurado=False,
        )

    asaas_configurado = bool((current_app.config.get("ASAAS_API_KEY") or "").strip())
    qtd_imoveis = _qtd_imoveis(user.owner_id)

    return render_template(
        "pagamento.html",
        user=user,
        bloqueado_ajudante=False,
        planos=planos.listar_planos(),
        plano_recomendado=planos.plano_recomendado(qtd_imoveis),
        qtd_imoveis=qtd_imoveis,
        assinatura_atual=_assinatura_atual(user.owner_id),
        asaas_configurado=asaas_configurado,
    )


@pagamento_bp.route("/pagamento/checkout", methods=["POST"])
@login_required
def checkout():
    user = db.session.get(User, session.get("user_id"))
    if not user:
        return redirect(url_for("auth.login"))

    if user.is_admin:
        return redirect(url_for("reservas.dashboard"))

    if user.e_ajudante:
        flash(
            t_flash(
                "Quem gerencia o pagamento é a conta principal que te convidou — "
                "fale com ela sobre o acesso."
            ),
            "erro",
        )
        return redirect(url_for("pagamento.pagina_pagamento"))

    plano_escolhido = (request.form.get("plano") or "").strip()
    if plano_escolhido not in planos.PLANOS:
        qtd_imoveis = _qtd_imoveis(user.owner_id)
        plano_escolhido = planos.plano_recomendado(qtd_imoveis)

    valor_cents = planos.valor_cents_do_plano(plano_escolhido)
    assinatura = _assinatura_atual(user.owner_id)

    try:
        if assinatura and assinatura.asaas_subscription_id and assinatura.status in (
            "pending", "active", "overdue",
        ):
            # Já tem assinatura viva na Asaas — é só uma troca de plano,
            # não precisa de checkout novo.
            asaas_service.atualizar_valor_assinatura(
                assinatura.asaas_subscription_id,
                valor_cents,
                atualizar_cobrancas_pendentes=True,
            )
            assinatura.plano = plano_escolhido
            assinatura.valor_cents = valor_cents
            db.session.commit()

            flash(t_flash("Plano atualizado com sucesso!"), "sucesso")
            return redirect(url_for("pagamento.pagina_pagamento"))

        resposta = asaas_service.criar_assinatura(user, valor_cents)
    except asaas_service.AsaasNaoConfigurado:
        flash(
            t_flash("O pagamento online ainda não foi configurado. Fale com o suporte."),
            "erro",
        )
        return redirect(url_for("pagamento.pagina_pagamento"))
    except asaas_service.AsaasErro as exc:
        current_app.logger.exception("Erro ao criar assinatura Asaas para user %s", user.id)
        flash(t_flash("Não foi possível iniciar a assinatura: %(erro)s", erro=str(exc)), "erro")
        return redirect(url_for("pagamento.pagina_pagamento"))

    asaas_subscription_id = resposta.get("id")
    if not asaas_subscription_id:
        flash(t_flash("A Asaas não retornou uma assinatura válida. Tente novamente."), "erro")
        return redirect(url_for("pagamento.pagina_pagamento"))

    proximo_vencimento = None
    data_bruta = resposta.get("nextDueDate")
    if data_bruta:
        try:
            proximo_vencimento = datetime.strptime(data_bruta, "%Y-%m-%d").date()
        except ValueError:
            proximo_vencimento = None

    nova_assinatura = Assinatura(
        user_id=user.owner_id,
        asaas_subscription_id=asaas_subscription_id,
        plano=plano_escolhido,
        valor_cents=valor_cents,
        ciclo="MONTHLY",
        status="pending",
        proximo_vencimento=proximo_vencimento,
    )
    db.session.add(nova_assinatura)
    db.session.commit()

    # A primeira cobrança (Payment) da assinatura já foi gerada
    # automaticamente pela Asaas — é nela que está o link de checkout.
    try:
        primeira_cobranca = asaas_service.obter_primeira_cobranca_assinatura(asaas_subscription_id)
    except asaas_service.AsaasErro:
        primeira_cobranca = None

    if primeira_cobranca:
        pagamento = Pagamento(
            user_id=user.owner_id,
            assinatura_id=nova_assinatura.id,
            asaas_customer_id=user.asaas_customer_id,
            asaas_payment_id=primeira_cobranca.get("id"),
            valor_cents=valor_cents,
            billing_type=primeira_cobranca.get("billingType"),
            invoice_url=primeira_cobranca.get("invoiceUrl"),
            status="pending",
        )
        db.session.add(pagamento)
        db.session.commit()

        if pagamento.invoice_url:
            return redirect(pagamento.invoice_url)

    flash(
        t_flash(
            "Assinatura criada! Assim que a primeira cobrança for gerada, "
            "você recebe o link de pagamento por e-mail."
        ),
        "sucesso",
    )
    return redirect(url_for("pagamento.pagina_pagamento"))


# ── Webhook Asaas (chamado pela Asaas, não por um usuário logado) ─────────

# Status da Asaas (maiúsculo) -> status interno (minúsculo, ver
# app/models/assinatura.py STATUS_VALIDOS).
_MAPA_STATUS_ASSINATURA = {
    "ACTIVE": "active",
    "EXPIRED": "expired",
    "OVERDUE": "overdue",
    "INACTIVE": "inactive",
}

# Enquanto a assinatura está "active" ou "overdue" (atraso recente,
# ainda dentro do período de tolerância da Asaas antes de expirar),
# mantemos o acesso liberado — só cortamos quando ela expira/inativa/
# cancela de verdade. Ajuste esse conjunto aqui se a regra de negócio
# mudar (ex.: cortar acesso assim que ficar "overdue").
_STATUS_QUE_LIBERAM_ACESSO = {"active", "overdue"}


def _webhook_autorizado() -> bool:
    token_esperado = (current_app.config.get("ASAAS_WEBHOOK_TOKEN") or "").strip()
    if not token_esperado:
        # Sem token configurado, aceitamos (ambiente de testes) — mas
        # assim que ASAAS_WEBHOOK_TOKEN existir, passa a ser obrigatório.
        return True

    token_recebido = (
        request.headers.get("asaas-access-token")
        or request.headers.get("Asaas-Access-Token")
        or request.args.get("token")
        or ""
    ).strip()
    return token_recebido == token_esperado


def _sincronizar_pagamento_ativo(assinatura: Assinatura) -> None:
    """Depois de mudar o status de uma Assinatura, propaga o resultado
    pra User.pagamento_ativo — que é o campo que o gate global de fato
    consulta (app/__init__.py gate_paywall)."""
    user = db.session.get(User, assinatura.user_id)
    if not user:
        return
    user.pagamento_ativo = assinatura.status in _STATUS_QUE_LIBERAM_ACESSO


@pagamento_bp.route("/webhooks/asaas", methods=["POST"])
@csrf.exempt
def webhook_asaas():
    if not _webhook_autorizado():
        return jsonify({"success": False, "message": "Não autorizado."}), 403

    corpo = request.get_json(silent=True) or {}
    evento = corpo.get("event", "")

    if evento.startswith("SUBSCRIPTION_"):
        return _tratar_webhook_assinatura(evento, corpo)

    if evento.startswith("PAYMENT_"):
        return _tratar_webhook_pagamento(evento, corpo)

    return jsonify({"success": True, "ignorado": True})


def _tratar_webhook_assinatura(evento: str, corpo: dict):
    subscription = corpo.get("subscription") or {}
    asaas_subscription_id = subscription.get("id")
    if not asaas_subscription_id:
        return jsonify({"success": True, "ignorado": True})

    assinatura = Assinatura.query.filter_by(
        asaas_subscription_id=asaas_subscription_id
    ).first()
    if not assinatura:
        current_app.logger.warning(
            "Webhook Asaas para assinatura desconhecida: %s", asaas_subscription_id
        )
        return jsonify({"success": True, "ignorado": True})

    if evento == "SUBSCRIPTION_DELETED":
        assinatura.status = "canceled"
        assinatura.cancelado_em = datetime.utcnow()
    else:
        status_bruto = subscription.get("status", "")
        assinatura.status = _MAPA_STATUS_ASSINATURA.get(status_bruto, assinatura.status)

    data_bruta = subscription.get("nextDueDate")
    if data_bruta:
        try:
            assinatura.proximo_vencimento = datetime.strptime(data_bruta, "%Y-%m-%d").date()
        except ValueError:
            pass

    _sincronizar_pagamento_ativo(assinatura)
    db.session.commit()
    return jsonify({"success": True})


def _tratar_webhook_pagamento(evento: str, corpo: dict):
    payment = corpo.get("payment") or {}
    asaas_payment_id = payment.get("id")
    if not asaas_payment_id:
        return jsonify({"success": True, "ignorado": True})

    pagamento = Pagamento.query.filter_by(asaas_payment_id=asaas_payment_id).first()
    if not pagamento:
        current_app.logger.warning(
            "Webhook Asaas para pagamento desconhecido: %s", asaas_payment_id
        )
        return jsonify({"success": True, "ignorado": True})

    novo_status = payment.get("status", pagamento.status)
    pagamento.status = novo_status.lower()

    if evento in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        pagamento.confirmado_em = datetime.utcnow()

        # A confirmação da 1ª cobrança de uma assinatura nova é o sinal
        # de que ela está de fato ativa (a Asaas só manda o
        # SUBSCRIPTION_UPDATED/ACTIVE separadamente, então liberamos o
        # acesso já aqui em vez de esperar os dois eventos).
        if pagamento.assinatura_id:
            assinatura = db.session.get(Assinatura, pagamento.assinatura_id)
            if assinatura and assinatura.status not in ("canceled",):
                assinatura.status = "active"
                _sincronizar_pagamento_ativo(assinatura)
        else:
            user = db.session.get(User, pagamento.user_id)
            if user:
                user.pagamento_ativo = True

    elif evento in ("PAYMENT_REFUNDED", "PAYMENT_DELETED", "PAYMENT_CHARGEBACK_REQUESTED"):
        if evento == "PAYMENT_REFUNDED" and not pagamento.assinatura_id:
            user = db.session.get(User, pagamento.user_id)
            if user:
                user.pagamento_ativo = False

    db.session.commit()
    return jsonify({"success": True})
