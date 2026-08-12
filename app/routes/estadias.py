"""
app/routes/estadias.py
Blueprint com CRUD completo de Estadias e seus Itens de Valor.
Todas as rotas exigem login e pertencem ao User da sessão.
"""

import re
from datetime import datetime, date

from flask import (
    Blueprint, jsonify, redirect, render_template,
    request, session, url_for, flash
)
from app.extensions import db
from app.models import User, Imovel
from app.models.estadia import Estadia, ItemEstadia
from app.utils import login_required, get_effective_owner_id

estadias_bp = Blueprint("estadias", __name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_brl(valor_str: str) -> float:
    """Converte '1.234,56' ou '1234.56' → float."""
    if not valor_str:
        return 0.0
    clean = re.sub(r"[^\d,.]", "", valor_str)
    if "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return 0.0


def _parse_date(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _imovel_do_user(imovel_id: int) -> Imovel:
    return Imovel.query.filter_by(
        id=imovel_id,
        user_id=get_effective_owner_id()
    ).first_or_404()


def _preencher_estadia(estadia: Estadia, form) -> None:
    estadia.nome_hospede  = form.get("nome_hospede", "").strip()
    estadia.email_hospede = form.get("email_hospede", "").strip() or None
    estadia.canal         = form.get("canal",    "Direto")
    estadia.perfil        = form.get("perfil",   "Novo")
    estadia.qtd_hospedes  = int(form.get("qtd_hospedes", 1) or 1)

    estadia.data_checkin  = _parse_date(form.get("data_checkin"))
    estadia.hora_checkin  = form.get("hora_checkin",  "14:00")
    estadia.data_checkout = _parse_date(form.get("data_checkout"))
    estadia.hora_checkout = form.get("hora_checkout", "11:00")

    qtd = form.get("quantidade_dias")
    if qtd:
        estadia.quantidade_dias = int(qtd)
    elif estadia.data_checkin and estadia.data_checkout:
        estadia.quantidade_dias = max(0, (estadia.data_checkout - estadia.data_checkin).days)

    estadia.moeda         = form.get("moeda", "BRL")
    estadia.valor_bruto   = _parse_brl(form.get("valor_bruto",   "0"))
    estadia.valor_liquido = _parse_brl(form.get("valor_liquido", "0"))

    estadia.tem_carro     = form.get("tem_carro", "Nao")
    estadia.tem_pet       = form.get("tem_pet",   "Nao")
    estadia.detalhe_pet   = form.get("detalhe_pet", "").strip() or None
    estadia.status        = form.get("status",    "confirmada")


def _salvar_itens(estadia_id: int) -> None:
    """Lê item_descricao[] / item_valor[] do formulário e persiste."""
    descricoes = request.form.getlist("item_descricao[]")
    valores    = request.form.getlist("item_valor[]")
    for desc, val in zip(descricoes, valores):
        desc = desc.strip()
        if not desc:
            continue
        item = ItemEstadia(estadia_id=estadia_id, descricao=desc)
        item.valor = _parse_brl(val)
        db.session.add(item)


# ── API — listagem por imóvel ─────────────────────────────────────────────────

@estadias_bp.route("/api/imovel/<int:imovel_id>/estadias")
@login_required
def api_listar_estadias(imovel_id: int):
    _imovel_do_user(imovel_id)
    estadias = (
        Estadia.query
        .filter_by(imovel_id=imovel_id, user_id=get_effective_owner_id())
        .order_by(Estadia.data_checkin.desc())
        .all()
    )
    return jsonify([e.to_dict() for e in estadias])


# ── API — detalhe de uma estadia ──────────────────────────────────────────────

@estadias_bp.route("/api/estadia/<int:id>")
@login_required
def api_detalhe_estadia(id: int):
    estadia = Estadia.query.filter_by(
        id=id,
        user_id=get_effective_owner_id()
    ).first_or_404()
    return jsonify(estadia.to_dict())


# ── CRIAR estadia ─────────────────────────────────────────────────────────────

@estadias_bp.route("/imovel/<int:imovel_id>/estadia/nova", methods=["POST"])
@login_required
def criar_estadia(imovel_id: int):
    _imovel_do_user(imovel_id)

    if not request.form.get("nome_hospede", "").strip():
        flash("Informe o nome do hóspede.", "erro")
        return redirect(url_for("imoveis.imoveis"))

    estadia = Estadia(imovel_id=imovel_id, user_id=get_effective_owner_id())
    _preencher_estadia(estadia, request.form)
    db.session.add(estadia)
    db.session.flush()          # gera estadia.id antes dos itens

    _salvar_itens(estadia.id)
    db.session.commit()

    flash("Estadia registrada com sucesso!", "sucesso")
    return redirect(url_for("imoveis.imoveis"))


# ── EDITAR estadia ────────────────────────────────────────────────────────────

@estadias_bp.route("/estadia/<int:id>/editar", methods=["POST"])
@login_required
def editar_estadia(id: int):
    estadia = Estadia.query.filter_by(
        id=id,
        user_id=get_effective_owner_id()
    ).first_or_404()

    _preencher_estadia(estadia, request.form)

    # Recria itens do zero
    ItemEstadia.query.filter_by(estadia_id=id).delete()
    _salvar_itens(id)

    db.session.commit()
    flash("Estadia atualizada!", "sucesso")
    return redirect(url_for("imoveis.imoveis"))


# ── EXCLUIR estadia ───────────────────────────────────────────────────────────

@estadias_bp.route("/estadia/<int:id>/excluir", methods=["POST"])
@login_required
def excluir_estadia(id: int):
    estadia = Estadia.query.filter_by(
        id=id,
        user_id=get_effective_owner_id()
    ).first_or_404()

    try:
        db.session.delete(estadia)   # cascade apaga os ItemEstadia
        db.session.commit()
        return jsonify({"success": True, "message": "Estadia removida."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ── API — stats mensais do imóvel ─────────────────────────────────────────────

@estadias_bp.route("/api/imovel/<int:imovel_id>/stats")
@login_required
def api_stats_imovel(imovel_id: int):
    import calendar as cal
    _imovel_do_user(imovel_id)

    hoje     = datetime.now()
    primeiro = hoje.replace(day=1).date()
    ultimo   = hoje.replace(day=cal.monthrange(hoje.year, hoje.month)[1]).date()
    total_dias_mes = cal.monthrange(hoje.year, hoje.month)[1]

    estadias = Estadia.query.filter_by(
        imovel_id=imovel_id,
        user_id=get_effective_owner_id()
    ).all()

    faturamento = 0.0
    dias_ocupados = 0

    for e in estadias:
        if not e.data_checkin or not e.data_checkout:
            continue
        if e.data_checkin <= ultimo and e.data_checkout >= primeiro:
            # Era e.valor_bruto — por isso esse card ("Faturamento Líquido")
            # mostrava um número diferente do total somado na aba Estadias
            # (que soma valor_liquido) pro mesmo imóvel. Os dois agora usam
            # a mesma métrica.
            faturamento   += e.valor_liquido
            inicio_ef      = max(e.data_checkin,  primeiro)
            fim_ef         = min(e.data_checkout, ultimo)
            dias_ocupados += max(0, (fim_ef - inicio_ef).days)

    ocupacao = min(100, round((dias_ocupados / total_dias_mes) * 100, 1))

    def fmt(v):
        s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"

    return jsonify({
        "ocupacao":    f"{ocupacao}%",
        "faturamento": fmt(faturamento),
        "dias_texto":  f"{dias_ocupados} dias",
    })