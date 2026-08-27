"""
app/routes/equipe.py
Hierarquia Proprietário / Anfitrião-ajudante:
  - Proprietário convida um Anfitrião-ajudante por e-mail.
  - Anfitrião aceita (logando ou criando conta) e passa a operar sobre os
    imóveis do Proprietário (ver User.owner_id / get_effective_owner_id).
  - Proprietário pode ver/remover ajudantes vinculados.
"""

from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash
)

from app.extensions import db
from app.models import User, ConviteAnfitriao
from app.utils import login_required, formatar_nome_exibicao, t_flash
from app.services.email_service import enviar_email_convite_anfitriao

equipe_bp = Blueprint("equipe", __name__)


def _usuario_atual() -> User | None:
    return db.session.get(User, session.get("user_id"))


def _e_proprietario(user: User) -> bool:
    """
    Só uma conta que NÃO é ajudante de ninguém (proprietario_id nulo) pode
    convidar/gerenciar a própria equipe de Anfitriões — evita aninhar
    hierarquias (ajudante convidando outro ajudante).
    """
    return user is not None and not user.e_ajudante


# =========================================================
# PÁGINA DA EQUIPE (Proprietário)
# =========================================================

@equipe_bp.route("/equipe")
@login_required
def equipe():
    user = _usuario_atual()
    if not _e_proprietario(user):
        flash(t_flash("Só a conta Proprietária pode gerenciar a equipe."), "erro")
        return redirect(url_for("reservas.dashboard"))

    anfitrioes = User.query.filter_by(proprietario_id=user.id).order_by(User.nome).all()
    convites_pendentes = (
        ConviteAnfitriao.query
        .filter_by(proprietario_id=user.id, status="pendente")
        .order_by(ConviteAnfitriao.created_at.desc())
        .all()
    )

    return render_template(
        "equipe.html",
        user=user,
        nome_usuario=formatar_nome_exibicao(user.nome),
        anfitrioes=anfitrioes,
        convites_pendentes=convites_pendentes,
    )


@equipe_bp.route("/equipe/convidar", methods=["POST"])
@login_required
def convidar():
    user = _usuario_atual()
    if not _e_proprietario(user):
        flash(t_flash("Só a conta Proprietária pode convidar Anfitriões."), "erro")
        return redirect(url_for("reservas.dashboard"))

    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash(t_flash("Informe um e-mail."), "erro")
        return redirect(url_for("equipe.equipe"))

    papel = (request.form.get("papel") or "anfitriao").strip().lower()
    if papel not in ("anfitriao", "auxiliar"):
        papel = "anfitriao"

    if email == (user.email or "").strip().lower():
        flash(t_flash("Você não pode convidar a si mesma(o)."), "erro")
        return redirect(url_for("equipe.equipe"))

    convidado = User.query.filter_by(email=email).first()
    if convidado and convidado.proprietario_id == user.id:
        flash(t_flash("Esse e-mail já é um Anfitrião da sua equipe."), "erro")
        return redirect(url_for("equipe.equipe"))
    if convidado and convidado.e_ajudante:
        flash(t_flash("Esse e-mail já está vinculado a outra conta Proprietária."), "erro")
        return redirect(url_for("equipe.equipe"))

    # Cancela convites pendentes duplicados pro mesmo e-mail antes de criar um novo
    ConviteAnfitriao.query.filter_by(
        proprietario_id=user.id, email=email, status="pendente"
    ).update({"status": "cancelado"})

    convite = ConviteAnfitriao(
        proprietario_id=user.id,
        email=email,
        token=ConviteAnfitriao.gerar_token(),
        papel=papel,
    )
    db.session.add(convite)
    db.session.commit()

    link = url_for("equipe.aceitar_convite_pagina", token=convite.token, _external=True)
    try:
        enviar_email_convite_anfitriao(
            destinatario=email,
            nome_proprietario=formatar_nome_exibicao(user.nome),
            link_convite=link,
            ja_tem_conta=bool(convidado),
            papel=papel,
        )
    except Exception:
        pass  # não bloqueia o fluxo se o e-mail falhar — o convite já existe

    flash(t_flash("Convite enviado para %(email)s.", email=email), "sucesso")
    return redirect(url_for("equipe.equipe"))


@equipe_bp.route("/equipe/convite/<int:convite_id>/cancelar", methods=["POST"])
@login_required
def cancelar_convite(convite_id):
    user = _usuario_atual()
    convite = ConviteAnfitriao.query.filter_by(id=convite_id, proprietario_id=user.id).first()
    if convite and convite.status == "pendente":
        convite.status = "cancelado"
        db.session.commit()
        flash(t_flash("Convite cancelado."), "sucesso")
    return redirect(url_for("equipe.equipe"))


@equipe_bp.route("/equipe/anfitriao/<int:anfitriao_id>/remover", methods=["POST"])
@login_required
def remover_anfitriao(anfitriao_id):
    user = _usuario_atual()
    ajudante = User.query.filter_by(id=anfitriao_id, proprietario_id=user.id).first()
    if not ajudante:
        flash(t_flash("Anfitrião não encontrado na sua equipe."), "erro")
        return redirect(url_for("equipe.equipe"))

    ajudante.proprietario_id = None
    db.session.commit()
    flash(t_flash("%(nome)s foi removido(a) da equipe.", nome=formatar_nome_exibicao(ajudante.nome)), "sucesso")
    return redirect(url_for("equipe.equipe"))


# =========================================================
# ACEITAR CONVITE (quem foi convidado)
# =========================================================

@equipe_bp.route("/convite-anfitriao/<token>")
def aceitar_convite_pagina(token):
    convite = ConviteAnfitriao.query.filter_by(token=token).first_or_404()

    if convite.status != "pendente" or convite.expirado():
        return render_template("convite_anfitriao.html", convite=None)

    usuario_logado_id = session.get("user_id")
    usuario_atual = db.session.get(User, usuario_logado_id) if usuario_logado_id else None

    email_bate = bool(
        usuario_atual and usuario_atual.email.strip().lower() == convite.email.strip().lower()
    )

    if not usuario_atual:
        # Guarda o token pra ser processado automaticamente assim que a
        # pessoa entrar (login) ou criar a conta (cadastro) — ver
        # criar_sessao() em app/routes/auth.py.
        session["convite_token_pendente"] = token

    return render_template(
        "convite_anfitriao.html",
        convite=convite,
        usuario_atual=usuario_atual,
        email_bate=email_bate,
    )


@equipe_bp.route("/convite-anfitriao/<token>/aceitar", methods=["POST"])
@login_required
def aceitar_convite(token):
    convite = ConviteAnfitriao.query.filter_by(token=token).first_or_404()
    user = _usuario_atual()

    if convite.status != "pendente" or convite.expirado():
        flash(t_flash("Esse convite não é mais válido."), "erro")
        return redirect(url_for("reservas.dashboard"))

    if user.email.strip().lower() != convite.email.strip().lower():
        flash(t_flash("Esse convite foi enviado para outro e-mail."), "erro")
        return redirect(url_for("reservas.dashboard"))

    user.proprietario_id = convite.proprietario_id
    # Quem aceita um convite passa a ser Anfitrião-ajudante ou Auxiliar
    # daquela conta, conforme o que foi escolhido no convite — travado
    # independente do que a pessoa tinha marcado antes (ver também
    # usuario.py, que impede voltar a marcar "Proprietário" ou trocar de
    # papel sozinho).
    user.categoria = "Auxiliar" if convite.papel == "auxiliar" else "Anfitrião"
    convite.status = "aceito"
    convite.aceito_em = datetime.utcnow()
    convite.anfitriao_id = user.id
    db.session.commit()

    session["user_categoria"] = user.categoria
    session.pop("convite_token_pendente", None)

    flash(t_flash("Convite aceito! Agora você opera junto com essa conta."), "sucesso")
    if user.categoria == "Auxiliar":
        return redirect(url_for("main.hub_anfitriao", tab="tarefas"))
    return redirect(url_for("reservas.dashboard"))
