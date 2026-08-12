"""
app/services/hospede_notificacoes.py
Motor de e-mails automáticos para o HÓSPEDE (não pro anfitrião):

  1. Guia pré-estadia — enviado N dias antes do check-in (configurável por
     imóvel), com o link do Guia Digital (o mesmo do QR code).
  2. Pedido de avaliação — enviado N dias depois do check-out, com um link
     público de avaliação. A resposta do hóspede volta pro anfitrião por
     e-mail e fica salva (Avaliacao) pra consulta posterior.

Como o projeto não tem um scheduler real (sem APScheduler/Celery, roda em
gunicorn multi-worker sem trava), esse motor é chamado de forma "oportunista"
a cada request autenticada (ver hook em app/__init__.py) em vez de um cron
de verdade. Isso cobre bem o caso comum (anfitrião navega o site com alguma
frequência), mas hóspedes de anfitriões totalmente inativos podem demorar
pra receber o e-mail até o próximo login dele. Tudo aqui é idempotente
(flags em Estadia) — chamar de novo nunca duplica um envio.
"""

from __future__ import annotations

from datetime import date, timedelta
import uuid

from flask import current_app

from app.extensions import db
from app.models import Imovel, Estadia, User
from app.services.email_service import (
    enviar_email_guia_hospede,
    enviar_email_solicitar_avaliacao,
)
from app.services.push_service import enviar_push_notificacao

DIAS_ANTES_GUIA_PADRAO = 1
DIAS_DEPOIS_AVALIACAO_PADRAO = 2


def processar_emails_hospede(user: User, base_url: str) -> dict:
    """
    Varre as Estadias do anfitrião e dispara os e-mails de hóspede que
    já venceram. `base_url` deve vir sem barra final (ex: request.host_url
    já sem a barra), usado para montar os links absolutos do e-mail.
    """
    hoje = date.today()
    resultado = {"guias_enviados": 0, "avaliacoes_solicitadas": 0}

    imoveis = Imovel.query.filter_by(user_id=user.id).all()
    imoveis_map = {im.id: im for im in imoveis}
    if not imoveis_map:
        return resultado

    houve_mudanca = False

    # ── 1) Guia pré-estadia ──────────────────────────────────────
    candidatos_guia = Estadia.query.filter(
        Estadia.user_id == user.id,
        Estadia.status.in_(["confirmada", "em_andamento"]),
        Estadia.email_guia_enviado.is_(False),
        Estadia.email_hospede.isnot(None),
        Estadia.email_hospede != "",
        Estadia.data_checkin >= hoje,
    ).all()

    for est in candidatos_guia:
        im = imoveis_map.get(est.imovel_id)
        if not im or not im.email_guia_ativo:
            continue

        dias_antes = im.email_guia_dias_antes if im.email_guia_dias_antes is not None else DIAS_ANTES_GUIA_PADRAO
        data_envio = est.data_checkin - timedelta(days=dias_antes)

        if hoje < data_envio:
            continue  # ainda não chegou a data de disparo

        if not im.slug_publico:
            im.gerar_slug()

        link_guia = f"{base_url}/g/{im.slug_publico}"

        try:
            enviar_email_guia_hospede(
                destinatario=est.email_hospede,
                nome_hospede=est.nome_hospede,
                imovel_titulo=im.titulo,
                link_guia=link_guia,
                data_checkin_fmt=est.data_checkin.strftime("%d/%m/%Y"),
                hora_checkin=est.hora_checkin,
            )
            est.email_guia_enviado = True
            resultado["guias_enviados"] += 1
            houve_mudanca = True

            # O e-mail vai pro HÓSPEDE (não tem conta/push no Nomdo) — o
            # anfitrião recebe um push só de "aviso", como espelho do que
            # já aconteceu automaticamente em nome dele.
            try:
                enviar_push_notificacao(
                    user,
                    titulo="Guia da estadia enviado",
                    corpo=f"Enviamos o guia digital pra {est.nome_hospede} ({im.titulo})",
                    url="/imoveis",
                    tag="nomdo-guia-hospede",
                )
            except Exception:
                current_app.logger.exception(
                    "Falha ao enviar push de guia pré-estadia para a estadia %s", est.id
                )
        except Exception:
            current_app.logger.exception(
                "Falha ao enviar guia pré-estadia para a estadia %s", est.id
            )

    # ── 2) Pedido de avaliação pós-estadia ───────────────────────
    candidatos_avaliacao = Estadia.query.filter(
        Estadia.user_id == user.id,
        Estadia.status.notin_(["cancelada", "bloqueio"]),
        Estadia.email_avaliacao_enviado.is_(False),
        Estadia.email_hospede.isnot(None),
        Estadia.email_hospede != "",
        Estadia.data_checkout <= hoje,
    ).all()

    for est in candidatos_avaliacao:
        im = imoveis_map.get(est.imovel_id)
        if not im or not im.email_avaliacao_ativo:
            continue

        dias_depois = (
            im.email_avaliacao_dias_depois
            if im.email_avaliacao_dias_depois is not None
            else DIAS_DEPOIS_AVALIACAO_PADRAO
        )
        data_envio = est.data_checkout + timedelta(days=dias_depois)

        if hoje < data_envio:
            continue

        if not est.token_avaliacao:
            est.token_avaliacao = uuid.uuid4().hex

        link_avaliacao = f"{base_url}/avaliar/{est.token_avaliacao}"

        try:
            enviar_email_solicitar_avaliacao(
                destinatario=est.email_hospede,
                nome_hospede=est.nome_hospede,
                imovel_titulo=im.titulo,
                link_avaliacao=link_avaliacao,
            )
            est.email_avaliacao_enviado = True
            resultado["avaliacoes_solicitadas"] += 1
            houve_mudanca = True

            try:
                enviar_push_notificacao(
                    user,
                    titulo="Pedido de avaliação enviado",
                    corpo=f"Pedimos pra {est.nome_hospede} avaliar a estadia em {im.titulo}",
                    url="/imoveis",
                    tag="nomdo-pedido-avaliacao",
                )
            except Exception:
                current_app.logger.exception(
                    "Falha ao enviar push de pedido de avaliação para a estadia %s", est.id
                )
        except Exception:
            current_app.logger.exception(
                "Falha ao enviar pedido de avaliação para a estadia %s", est.id
            )

    if houve_mudanca:
        db.session.commit()

    return resultado
