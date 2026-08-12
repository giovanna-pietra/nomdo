"""
app/routes/push.py
Inscrição/cancelamento de notificações push do navegador (Web Push) e o
Service Worker que recebe essas notificações — inclusive com a aba/o
navegador fechados.

Diferente de app/routes/api.py (blueprint do app mobile, autenticado por
Bearer token e isento de CSRF de propósito), aqui quem chama é o próprio
site, autenticado pela sessão de cookie normal — por isso o CSRF fica
ativo (o token vem no header X-CSRFToken, enviado pelo JS em
app/static/js/push.js a partir de uma meta tag).
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, session, send_from_directory

from app.extensions import db
from app.models import PushSubscription, User
from app.services.push_service import enviar_push_notificacao
from app.utils import login_required

push_bp = Blueprint("push", __name__)


@push_bp.route("/push/vapid-public-key")
@login_required
def vapid_public_key():
    return jsonify({"publicKey": current_app.config.get("VAPID_PUBLIC_KEY") or ""})


@push_bp.route("/push/subscribe", methods=["POST"])
@login_required
def subscribe():
    user_id = session.get("user_id")
    dados = request.get_json(silent=True) or {}

    endpoint = dados.get("endpoint")
    keys = dados.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"success": False, "message": "Inscrição de push inválida."}), 400

    inscricao = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if inscricao:
        # Já existia (outro usuário no mesmo navegador, ou reinscrição) —
        # atualiza o dono e as chaves em vez de duplicar.
        inscricao.user_id = user_id
        inscricao.p256dh = p256dh
        inscricao.auth = auth
        inscricao.user_agent = (request.user_agent.string or "")[:255]
    else:
        inscricao = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=(request.user_agent.string or "")[:255],
        )
        db.session.add(inscricao)

    db.session.commit()
    return jsonify({"success": True})


@push_bp.route("/push/unsubscribe", methods=["POST"])
@login_required
def unsubscribe():
    dados = request.get_json(silent=True) or {}
    endpoint = dados.get("endpoint")

    query = PushSubscription.query.filter_by(user_id=session.get("user_id"))
    if endpoint:
        query = query.filter_by(endpoint=endpoint)

    removidas = query.delete(synchronize_session=False)
    db.session.commit()

    return jsonify({"success": True, "removidas": removidas})


@push_bp.route("/push/enviar-teste", methods=["POST"])
@login_required
def enviar_teste():
    """
    Dispara uma notificação push de teste pro próprio usuário logado —
    usado pelo botão "Enviar notificação de teste" em Configurações, pra
    confirmar de verdade (fora do navegador, inclusive com a aba fechada)
    que a inscrição está funcionando, sem precisar esperar um evento real
    do Hub/estadia disparar.
    """
    user = db.session.get(User, session.get("user_id"))
    if not user:
        return jsonify({"success": False, "message": "Sessão inválida."}), 401

    if not user.notify_browser:
        return jsonify({
            "success": False,
            "message": "Notificações no navegador estão desligadas nas suas Configurações.",
        }), 400

    tem_inscricao = PushSubscription.query.filter_by(user_id=user.id).first() is not None
    if not tem_inscricao:
        return jsonify({
            "success": False,
            "message": "Nenhuma inscrição de push encontrada — ative o toggle primeiro.",
        }), 400

    resultado = enviar_push_notificacao(
        user,
        titulo="🔔 Notificação de teste",
        corpo="Se você está vendo isso, as notificações push estão funcionando — mesmo com a aba fechada.",
        url="/configuracoes",
        tag="nomdo-teste",
    )

    if resultado["enviadas"] == 0:
        if resultado["erros"]:
            # Erro de verdade na entrega (não é só inscrição expirada) —
            # mostra o motivo real em vez de um "tente de novo" genérico.
            mensagem = "Falha ao entregar: " + " | ".join(resultado["erros"])
        elif resultado["removidas"] > 0:
            mensagem = "A inscrição estava expirada e foi removida — ative o toggle de novo pra reinscrever."
        else:
            mensagem = "Não foi possível entregar (motivo desconhecido) — confira o log do servidor."

        return jsonify({
            "success": False,
            "message": mensagem,
            "detalhe": resultado,
        }), 502

    return jsonify({"success": True, **resultado})


@push_bp.route("/sw.js")
def service_worker():
    """
    Serve o Service Worker na raiz do site (não em /static/sw.js) pra que
    o escopo padrão dele cubra o site inteiro — o navegador define o
    escopo com base na URL de onde o arquivo foi servido, não em onde ele
    fisicamente mora no disco.
    """
    resposta = send_from_directory(current_app.static_folder, "sw.js")
    # Redundante servindo já na raiz (o escopo padrão já seria "/"), mas
    # explícito não faz mal e documenta a intenção.
    resposta.headers["Service-Worker-Allowed"] = "/"
    return resposta
