from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    session
)

from app.extensions import db
from app.models import User
from app.utils import login_required, formatar_nome_exibicao
from app.utils.i18n import t_flash
from app.services import enviar_email_suporte


suporte_bp = Blueprint(
    "suporte",
    __name__
)


@suporte_bp.route("/suporte", methods=["GET", "POST"])
@login_required
def chamado():

    user = db.session.get(
        User,
        session["user_id"]
    )

    arquivos = request.files.getlist("anexos")

    if request.method == "POST":

        assunto = request.form.get("assunto")
        mensagem = request.form.get("mensagem")

        enviar_email_suporte(
            nome=user.nome,
            email_usuario=user.email,
            tipo_contato=request.form.get("tipo_contato", ""),
            contato=request.form.get("contato", ""),
            mensagem=mensagem,
            lista_anexos=arquivos,
        )

        flash(
            t_flash("Chamado enviado com sucesso!"),
            "sucesso"
        )

        return redirect(
            url_for("suporte.chamado")
        )

    return render_template(
        "chamado.html",
        user=user,
        nome_usuario=formatar_nome_exibicao(user.nome),
        categoria_usuario=user.categoria
    )