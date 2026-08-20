"""
app/routes/cron.py
Endpoint interno para disparo agendado das checagens que dependem só da
data (troca de pilha de fechadura, limpeza pós-checkout e rotinas do Hub;
e-mails ao hóspede — guia pré-estadia e pedido de avaliação).

O projeto não tem um scheduler nativo (sem cron/APScheduler/Celery), então
esse endpoint existe pra ser chamado 1x por dia por um agendador externo
(ex: um scheduled task do Cowork fazendo um POST aqui). Antes disso, essas
checagens só rodavam "de carona" quando o próprio anfitrião navegava pelo
site — o que atrasava os e-mails se ele ficasse muito tempo sem acessar.

Não tem login de usuário (quem chama é um robô, não uma sessão autenticada),
então a proteção é por segredo compartilhado (CRON_SECRET), enviado no
header X-Cron-Secret ou na query string (?secret=...).

Tudo aqui reaproveita o mesmo motor idempotente já usado nos outros
gatilhos (processar_lembretes / processar_emails_hospede) — chamar de novo
não duplica tarefa nem e-mail.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.models import User
from app.routes.hub import processar_lembretes, processar_push_checkin_hoje
from app.services.hospede_notificacoes import processar_emails_hospede
from app.services.documentos_service import (
    processar_formularios_documentos, apagar_documentos_antigos,
)

cron_bp = Blueprint("cron", __name__)


def _autorizado() -> bool:
    secret_esperado = (current_app.config.get("CRON_SECRET") or "").strip()
    if not secret_esperado:
        # Sem CRON_SECRET configurado no ambiente, o endpoint fica desativado
        # por segurança (evita expor um gatilho aberto sem proteção).
        return False

    secret_recebido = (
        request.headers.get("X-Cron-Secret")
        or request.args.get("secret")
        or ""
    ).strip()
    return secret_recebido == secret_esperado


@cron_bp.route("/api/cron/processar-lembretes", methods=["GET", "POST"])
def processar_lembretes_globais():
    if not _autorizado():
        return jsonify({"success": False, "message": "Não autorizado."}), 403

    base_url = (
        current_app.config.get("APP_BASE_URL")
        or request.host_url.rstrip("/")
    )

    resumo = {
        "usuarios_processados": 0,
        "tarefas_hub_criadas": 0,
        "guias_enviados": 0,
        "avaliacoes_solicitadas": 0,
        "convites_documentos_enviados": 0,
        "avisos_checkin_enviados": 0,
        "documentos_formularios_limpos": 0,
        "documentos_arquivos_apagados": 0,
        "erros": 0,
    }

    usuarios = User.query.all()
    for user in usuarios:
        try:
            r_hub = processar_lembretes(user)
            resumo["tarefas_hub_criadas"] += r_hub.get("tarefas_criadas", 0)
        except Exception:
            resumo["erros"] += 1
            current_app.logger.exception(
                "Falha ao processar lembretes do Hub para o usuário %s", user.id
            )

        try:
            r_checkin = processar_push_checkin_hoje(user)
            resumo["avisos_checkin_enviados"] += r_checkin.get("avisos_enviados", 0)
        except Exception:
            resumo["erros"] += 1
            current_app.logger.exception(
                "Falha ao processar push de check-in do dia para o usuário %s", user.id
            )

        try:
            r_hosp = processar_emails_hospede(user, base_url)
            resumo["guias_enviados"] += r_hosp.get("guias_enviados", 0)
            resumo["avaliacoes_solicitadas"] += r_hosp.get("avaliacoes_solicitadas", 0)
        except Exception:
            resumo["erros"] += 1
            current_app.logger.exception(
                "Falha ao processar e-mails de hóspede para o usuário %s", user.id
            )

        try:
            r_doc = processar_formularios_documentos(user, base_url)
            resumo["convites_documentos_enviados"] += r_doc.get("convites_enviados", 0)
        except Exception:
            resumo["erros"] += 1
            current_app.logger.exception(
                "Falha ao processar formulários de documentos para o usuário %s", user.id
            )

        try:
            r_limpeza = apagar_documentos_antigos(user)
            resumo["documentos_formularios_limpos"] += r_limpeza.get("formularios_limpos", 0)
            resumo["documentos_arquivos_apagados"] += r_limpeza.get("arquivos_apagados", 0)
        except Exception:
            resumo["erros"] += 1
            current_app.logger.exception(
                "Falha ao apagar documentos antigos do usuário %s", user.id
            )

        resumo["usuarios_processados"] += 1

    current_app.logger.info("Cron diário de lembretes/e-mails concluído: %s", resumo)
    return jsonify({"success": True, **resumo})
