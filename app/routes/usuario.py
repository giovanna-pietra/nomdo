"""
app/routes/usuario.py
Blueprint de gerenciamento do perfil do usuário.
"""

import os
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, current_app,
)
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import User
from app.utils import (
    login_required,
    salvar_arquivo,
    deletar_arquivo,
    formatar_nome_exibicao,
    idade_minima_atingida,
    IDADE_MINIMA_CADASTRO,
    t_flash,
)

from app.services import enviar_email_despedida

usuario_bp = Blueprint("usuario", __name__)


# ==========================================================
# PERFIL
# ==========================================================

@usuario_bp.route("/usuario", methods=["GET", "POST"])
@login_required
def usuario():

    user = db.session.get(User, session["user_id"])

    # Segunda trava (além do gate global em app/__init__.py): se o perfil
    # ainda está incompleto, nem renderiza a tela de perfil (com menu
    # completo) — manda direto pra completar-perfil. Fica redundante com o
    # gate global de propósito, pra não depender só dele.
    if not user.telefone or not user.data_nascimento or not user.genero:
        return redirect(url_for("usuario.completar_perfil"))

    if request.method == "POST":

        foto = request.files.get("foto")

        print("REQUEST FILES:", request.files)
        print("FOTO:", foto)

        # ==================================================
        # REMOVER FOTO
        # ==================================================

        if request.form.get("remover_foto") == "1":

            if user.foto:

                deletar_arquivo(user.foto)

            user.foto = None

        # ==================================================
        # NOVA FOTO
        # ==================================================

        elif foto and foto.filename:

            # remove antiga
            if user.foto:

                deletar_arquivo(user.foto)

            filename = salvar_arquivo(foto)

            if filename:

                # Antes gravava com o prefixo "uploads/" embutido — agora
                # grava só o nome puro, igual a Imovel.foto_principal (fica
                # consistente, e o filtro url_upload normaliza os dois jeitos
                # ao montar a URL, então contas antigas continuam exibindo
                # a foto certinho).
                user.foto = filename

        # ==================================================
        # DADOS
        # ==================================================

        user.nome = request.form.get(
            "nome",
            ""
        ).strip()

        user.email = request.form.get(
            "email",
            ""
        ).strip().lower()

        user.telefone = request.form.get(
            "telefone_completo"
        )

        user.genero = request.form.get(
            "genero"
        )

        categoria_escolhida = request.form.get("categoria", "").strip()

        # Só "Anfitrião" ou "Proprietário" são valores válidos — qualquer
        # outra coisa (form adulterado, campo vazio) mantém o valor atual
        # em vez de gravar lixo. Uma conta Anfitrião-ajudante (vinculada a
        # outro Proprietário) nunca pode virar "Proprietário" por aqui —
        # a categoria dela é sempre travada em "Anfitrião" (ver equipe.py).
        if user.e_ajudante:
            user.categoria = "Anfitrião"
        elif categoria_escolhida in ("Anfitrião", "Proprietário"):
            user.categoria = categoria_escolhida

        # Garante que o SQLAlchemy identifique a alteração da string de categoria
        flag_modified(user, "categoria")

        # ==================================================
        # DATA NASCIMENTO
        # ==================================================

        data_nasc = request.form.get(
            "data_nascimento"
        )

        if data_nasc:

            user.data_nascimento = datetime.strptime(
                data_nasc,
                "%Y-%m-%d"
            ).date()

        # Troca de senha saiu daqui — agora só é possível via "Esqueci minha
        # senha" (fluxo por código de verificação, ver auth.esqueci_senha /
        # auth.resetar_senha), pra não deixar um campo de senha exposto
        # dentro da tela de perfil.

        db.session.commit()

        # ==================================================
        # CORREÇÃO CRUCIAL: SINCRONIZAR SESSÃO DO COOKIE
        # ==================================================
        # Se a sua base_dash usa dados da session para montar menus/perfil,
        # precisamos atualizar essas chaves para que a alteração persista pós-logout.
        session["user_nome"] = user.nome
        session["user_email"] = user.email
        session["user_categoria"] = user.categoria
        if user.foto:
            session["user_foto"] = user.foto
        else:
            session.pop("user_foto", None)

        flash(
            "Perfil updated com sucesso!",
            "sucesso"
        )

        return redirect(
            url_for("usuario.usuario")
        )

    return render_template(
        "usuario.html",
        user=user,
        nome_usuario=formatar_nome_exibicao(user.nome),
        categoria_usuario=user.categoria,
    )


# ==========================================================
# COMPLETAR PERFIL (telefone + data de nascimento + gênero obrigatórios)
# ==========================================================
# Toda conta precisa ter telefone, data de nascimento e gênero preenchidos —
# contas criadas pelo Google nunca vêm com esses dados, e contas antigas de
# cadastro manual também podem estar sem eles (o formulário nem sempre teve
# esses campos até essa correção). O gate global em app/__init__.py
# redireciona pra cá sempre que um desses três estiver faltando.

@usuario_bp.route("/completar-perfil", methods=["GET", "POST"])
@login_required
def completar_perfil():

    user = db.session.get(User, session["user_id"])

    if request.method == "POST":

        telefone = (request.form.get("telefone_completo") or "").strip()
        data_nasc = (request.form.get("data_nascimento") or "").strip()
        genero = (request.form.get("genero") or "").strip()

        if not telefone or not data_nasc or not genero:
            flash(
                t_flash("Telefone, data de nascimento e gênero são obrigatórios."),
                "erro"
            )
            return redirect(url_for("usuario.completar_perfil"))

        # Idade mínima de cadastro (13 anos) — pega aqui quem entrou pelo
        # Google, já que o Google não manda data de nascimento no login
        # (essa é a primeira vez que a conta informa a data de fato).
        if not idade_minima_atingida(data_nasc):
            flash(
                t_flash("Você precisa ter pelo menos %(idade)s anos para usar o Nomdo.", idade=IDADE_MINIMA_CADASTRO),
                "erro"
            )
            return redirect(url_for("usuario.completar_perfil"))

        user.telefone = telefone
        user.data_nascimento = datetime.strptime(
            data_nasc,
            "%Y-%m-%d"
        ).date()
        user.genero = genero

        db.session.commit()

        flash(
            t_flash("Perfil completo! Obrigado."),
            "sucesso"
        )

        return redirect(
            url_for("reservas.dashboard")
        )

    return render_template(
        "completar_perfil.html",
        user=user,
        nome_usuario=formatar_nome_exibicao(user.nome),
    )


# ==========================================================
# EXCLUIR CONTA
# ==========================================================

@usuario_bp.route("/excluir_conta", methods=["POST"])
@login_required
def excluir_conta():

    user = db.session.get(
        User,
        session["user_id"]
    )

    try:

        email_usuario = user.email

        nome_usuario = formatar_nome_exibicao(
            user.nome
        )

        # ==================================================
        # FOTO PERFIL
        # ==================================================

        if user.foto:

            deletar_arquivo(user.foto)

        # ==================================================
        # FOTOS IMÓVEIS
        # ==================================================

        for imovel in user.imoveis:

            if imovel.foto_principal:

                deletar_arquivo(
                    imovel.foto_principal
                )

        # ==================================================
        # DELETE USER
        # ==================================================

        db.session.delete(user)

        db.session.commit()

        enviar_email_despedida(
            email_usuario,
            nome_usuario
        )

        session.clear()

        return redirect(
            url_for("auth.login")
        )

    except Exception as exc:

        db.session.rollback()

        if user:
            current_app.logger.error(
                "Erro ao excluir conta user_id=%s: %s",
                user.id,
                exc
            )

        flash(
            "Erro ao excluir conta. Tente novamente.",
            "erro"
        )

        return redirect(
            url_for("usuario.usuario")
        )