"""
app/routes/documentos.py
Rota pública do Formulário de Documentos do Hóspede — genérico e
customizável pelo anfitrião (RG/CPF, placa do carro, foto do pet etc,
conforme Imovel.documentos_campos). O hóspede acessa pelo link recebido
por e-mail antes do check-in (ver app/services/documentos_service.py).
Sem @login_required: quem acessa é o hóspede, não o anfitrião. O link
expira alguns dias depois do check-out (FormularioDocumentos.expira_em).
"""
from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for

from app.extensions import db
from app.models import FormularioDocumentos
from app.services.documentos_service import campos_do_imovel
from app.utils import salvar_arquivo, deletar_arquivo

documentos_bp = Blueprint("documentos", __name__)


@documentos_bp.route("/documentos/<string:token>")
def pagina_formulario(token):
    form = FormularioDocumentos.query.filter_by(token=token).first_or_404()
    imovel = form.imovel
    estadia = form.estadia

    expirado = (
        form.status != "respondido"
        and form.expira_em is not None
        and date.today() > form.expira_em
    )

    link_guia = None
    if form.status == "respondido" and imovel and imovel.slug_publico:
        link_guia = url_for("guia_publico.guia_hospede", slug=imovel.slug_publico)

    campos = campos_do_imovel(imovel) if imovel else []

    return render_template(
        "documentos_hospede.html",
        form=form,
        imovel=imovel,
        estadia=estadia,
        campos=campos,
        expirado=expirado,
        link_guia=link_guia,
        token=token,
    )


@documentos_bp.route("/documentos/<string:token>", methods=["POST"])
def enviar_formulario(token):
    form = FormularioDocumentos.query.filter_by(token=token).first_or_404()

    # Idempotência: já respondeu, não deixa sobrescrever.
    if form.status == "respondido":
        return redirect(url_for("documentos.pagina_formulario", token=token))

    # Expirado: não aceita mais envios.
    if form.expira_em is not None and date.today() > form.expira_em:
        return redirect(url_for("documentos.pagina_formulario", token=token))

    imovel = form.imovel
    campos = campos_do_imovel(imovel) if imovel else []

    respostas = []
    faltando = []
    for i, campo in enumerate(campos):
        campo_nome = f"campo_{i}"
        if campo["tipo"] == "foto":
            arquivo = request.files.get(campo_nome)
            valor = salvar_arquivo(arquivo) if arquivo and arquivo.filename else ""
        else:
            valor = (request.form.get(campo_nome) or "").strip()

        if campo["obrigatorio"] and not valor:
            faltando.append(str(i))

        respostas.append({
            "nome": campo["nome"],
            "tipo": campo["tipo"],
            "obrigatorio": campo["obrigatorio"],
            "valor": valor,
        })

    # Validação no servidor — o atributo `required` do HTML (só no
    # navegador) não impede um POST direto sem passar pelo formulário.
    # Sem isso, dava pra marcar como "respondido" sem enviar nenhum dos
    # documentos obrigatórios (ex: RG/CPF).
    if faltando:
        # Alguma FOTO de um campo opcional pode já ter sido salva em disco
        # nesta mesma tentativa (antes de sabermos que outro campo
        # obrigatório estava faltando) — remove pra não acumular arquivo
        # órfão, já que essa resposta não vai ser gravada.
        for resposta in respostas:
            if resposta["tipo"] == "foto" and resposta["valor"]:
                deletar_arquivo(resposta["valor"])

        return redirect(url_for(
            "documentos.pagina_formulario",
            token=token,
            erro="obrigatorio",
            faltando=",".join(faltando),
        ))

    form.respostas = respostas
    form.status = "respondido"
    form.respondido_em = datetime.utcnow()
    db.session.commit()

    return redirect(url_for("documentos.pagina_formulario", token=token))
