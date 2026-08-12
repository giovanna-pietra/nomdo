"""
app/services/push_service.py
Serviço centralizado de envio de notificações push do navegador (Web Push
+ VAPID), via pywebpush. Funciona mesmo com o navegador/aba fechados —
é o próprio serviço de push do navegador (Chrome/FCM, Firefox/Mozilla
etc.) que entrega e acorda o Service Worker.

Sem VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY configuradas, `enviar_push_notificacao`
simplesmente não faz nada (log de aviso) — não quebra o fluxo do chamador,
igual ao padrão já usado pelo `email_service` quando falha o SMTP.
"""

from __future__ import annotations

import json

from flask import current_app

try:
    from pywebpush import webpush, WebPushException
except ImportError:  # pragma: no cover - só acontece se a dependência não foi instalada ainda
    webpush = None
    WebPushException = Exception


def _vapid_configurado() -> bool:
    return bool(
        current_app.config.get("VAPID_PUBLIC_KEY")
        and current_app.config.get("VAPID_PRIVATE_KEY")
    )


def enviar_push_notificacao(
    user,
    titulo: str,
    corpo: str,
    url: str | None = None,
    tag: str | None = None,
) -> dict:
    """
    Envia uma notificação push pra todas as inscrições ativas do usuário
    (pode ter mais de um navegador/dispositivo inscrito), respeitando o
    toggle `user.notify_browser` — mesmo padrão do `notify_email` pros
    e-mails.

    Retorno
    -------
    dict : {"enviadas": int, "removidas": int, "erros": list[str]} — nunca
           lança exceção pro chamador (erros de rede/subscription expirada
           são só logados, igual ao `_smtp_enviar`). `erros` traz o motivo
           de cada falha (além do log), útil pro botão "Testar" mostrar
           algo além de "não deu" na hora de diagnosticar.
    """
    resultado = {"enviadas": 0, "removidas": 0, "erros": []}

    if not user or not getattr(user, "notify_browser", False):
        return resultado

    if webpush is None:
        mensagem = (
            "pywebpush não está instalado no ambiente Python que está rodando "
            "o Flask (rode: pip install -r requirements.txt) — notificação push ignorada."
        )
        current_app.logger.warning(mensagem)
        resultado["erros"].append(mensagem)
        return resultado

    if not _vapid_configurado():
        mensagem = (
            "VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY não configuradas neste processo "
            "(confira o .env e REINICIE o Flask — variável de ambiente só carrega "
            "no início do processo) — notificação push ignorada."
        )
        current_app.logger.warning(mensagem)
        resultado["erros"].append(mensagem)
        return resultado

    # Import local pra evitar import circular (push_service <-> models/extensions).
    from app.extensions import db
    from app.models import PushSubscription

    inscricoes = PushSubscription.query.filter_by(user_id=user.id).all()
    if not inscricoes:
        resultado["erros"].append(
            "Nenhuma inscrição de push encontrada pra este usuário no banco."
        )
        return resultado

    payload = json.dumps({
        "title": titulo,
        "body": corpo,
        "url": url or "/hub-anfitriao",
        "tag": tag or "nomdo-notificacao",
    })

    vapid_claims = {
        "sub": f"mailto:{current_app.config.get('VAPID_ADMIN_EMAIL') or 'contato@nomdo.app'}"
    }

    houve_remocao = False

    for inscricao in inscricoes:
        try:
            webpush(
                subscription_info=inscricao.to_subscription_info(),
                data=payload,
                vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],
                vapid_claims=dict(vapid_claims),
                # Bug conhecido do pywebpush (nunca corrigido na lib, até a
                # 2.3.0): o WNS (serviço de push do Edge/Windows) exige o
                # header X-WNS-Cache-Policy — sem ele, rejeita com 400 "Ttl
                # value conflicts with X-WNS-Cache-Policy" mesmo com tudo
                # certo (chaves VAPID válidas, inscrição válida etc.).
                # Endpoints de outros navegadores (Chrome/FCM, Firefox)
                # ignoram esse header, então é seguro mandar sempre.
                headers={"X-WNS-Cache-Policy": "no-cache"},
            )
            resultado["enviadas"] += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            corpo_resposta = getattr(getattr(exc, "response", None), "text", "") or ""
            if status_code in (404, 410):
                # Inscrição expirada/revogada pelo navegador — não adianta
                # tentar de novo, remove pra não acumular lixo na tabela.
                db.session.delete(inscricao)
                resultado["removidas"] += 1
                houve_remocao = True
            else:
                mensagem = f"HTTP {status_code}: {corpo_resposta or exc}"
                current_app.logger.warning(
                    "Falha ao enviar push pro usuário %s: %s", user.id, mensagem
                )
                resultado["erros"].append(mensagem)
        except Exception as exc:
            current_app.logger.warning(
                "Erro inesperado ao enviar push pro usuário %s: %s", user.id, exc
            )
            resultado["erros"].append(f"{type(exc).__name__}: {exc}")

    if houve_remocao:
        db.session.commit()

    return resultado
