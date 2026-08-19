from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, session, abort, redirect, url_for, flash, request, current_app
from functools import wraps
from app.extensions import db
from app.models import User, Imovel, Estadia
from sqlalchemy import func

from app.utils.auth import login_required  # Injeção necessária para processamento de agregação
from app.utils.i18n import t_flash

admin_bp = Blueprint('admin', __name__)

ADMIN_EMAILS = ("grouppietra@gmail.com", "giovanna.perovano@clona.com.br")


def admin_required(f):
    @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_email = (session.get("user_email") or "").lower()
        if session.get("is_admin") is True:
            return f(*args, **kwargs)

        if user_email and user_email in ADMIN_EMAILS:
            return f(*args, **kwargs)

        user_id = session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if user and (getattr(user, "is_admin", False) or user.email.lower() in ADMIN_EMAILS):
                session["is_admin"] = True
                return f(*args, **kwargs)

        abort(403)
    return decorated_function


master_required = admin_required

# --- DASHBOARD PRINCIPAL ---
@admin_bp.route('/admin/dashboard')
@admin_required
@login_required
def dashboard():
    today = date.today()
    start_month = today.replace(day=1)
    last_30_days = datetime.utcnow() - timedelta(days=30)

    total_usuarios = User.query.count()
    usuarios_ativos = User.query.filter_by(is_active=True).count()
    usuarios_admin = User.query.filter_by(is_admin=True).count()

    novos_mes = User.query.filter(User.created_at >= start_month).count()
    novos_30d = User.query.filter(User.created_at >= last_30_days).count()

    total_imoveis = Imovel.query.count()
    total_estadias = Estadia.query.count()

    # ---- PROCESSAMENTO DO RENDIMENTO TOTAL (SOMA DAS ESTADIAS) ----
    # NOTA: isso costumava somar o modelo "Reserva" (agenda de viagens
    # pessoais do usuário, sem relação real com os imóveis — removido do
    # sistema). O dado real de faturamento é a Estadia (valor_bruto_cents).
    faturamento_bruto_cents = (
        db.session.query(func.sum(Estadia.valor_bruto_cents))
        .filter(Estadia.status != "cancelada")
        .scalar() or 0
    )
    faturamento_bruto = faturamento_bruto_cents / 100
    faturamento_formatado = f"{faturamento_bruto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Ocupação aproximada: % de imóveis com estadia ativa hoje
    estadias_hoje = Estadia.query.filter(
        Estadia.status != "cancelada",
        Estadia.data_checkin <= today,
        Estadia.data_checkout >= today,
    ).count()
    ocupacao = 0
    if total_imoveis:
        ocupacao = round((estadias_hoje / total_imoveis) * 100)

    # ---- ARQUITETURA DEMOGRÁFICA: FAIXA ETÁRIA COMPUTAÇÃO DYNAMIC ----
    f_18_24 = 0
    f_25_34 = 0
    f_35_44 = 0
    f_45_54 = 0
    f_55_mais = 0

    usuarios_datas = db.session.query(User.data_nascimento).filter(User.data_nascimento.isnot(None)).all()
    
    for registro in usuarios_datas:
        data_nasc = registro[0]
        if data_nasc:
            idade = today.year - data_nasc.year - ((today.month, today.day) < (data_nasc.month, data_nasc.day))
            if 18 <= idade <= 24:
                f_18_24 += 1
            elif 25 <= idade <= 34:
                f_25_34 += 1
            elif 35 <= idade <= 44:
                f_35_44 += 1
            elif 45 <= idade <= 54:
                f_45_54 += 1
            elif idade >= 55:
                f_55_mais += 1

    faixas_etarias = [f_18_24, f_25_34, f_35_44, f_45_54, f_55_mais]

    # ---- ARQUITETURA DEMOGRÁFICA: GÊNERO COMPUTAÇÃO DYNAMIC ----
    qtd_feminino = User.query.filter(func.lower(User.genero) == 'feminino').count()
    qtd_masculino = User.query.filter(func.lower(User.genero) == 'masculino').count()
    qtd_outros = total_usuarios - (qtd_feminino + qtd_masculino)
    
    distribuicao_genero = [qtd_feminino, qtd_masculino, qtd_outros]

    stats = {
        "total_usuarios": total_usuarios,
        "usuarios_ativos": usuarios_ativos,
        "usuarios_admin": usuarios_admin,
        "novos_mes": novos_mes,
        "novos_30d": novos_30d,
        "total_imoveis": total_imoveis,
        "total_estadias": total_estadias,
        "faturamento": faturamento_formatado,
        "chamados": 0,
        "ocupacao": ocupacao,
        "cancelamentos": 0,
        "faixas_etarias": faixas_etarias,
        "distribuicao_genero": distribuicao_genero
    }

    usuarios_recentes = (
        User.query.order_by(User.created_at.desc())
        .limit(8)
        .all()
    )

    labels = []
    users_by_month = []
    estadias_by_month = []
    now = datetime.utcnow()
    for i in range(11, -1, -1):
        month_start = (now.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        labels.append(month_start.strftime("%b/%y"))

        users_by_month.append(
            User.query.filter(User.created_at >= month_start, User.created_at < next_month).count()
        )
        estadias_by_month.append(
            Estadia.query.filter(Estadia.criado_em >= month_start, Estadia.criado_em < next_month).count()
        )

    chart = {
        "labels": labels,
        "users_by_month": users_by_month,
        "estadias_by_month": estadias_by_month,
        "values": estadias_by_month
    }

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        usuarios_recentes=usuarios_recentes,
        faturamento_chart=chart,
        estadias_chart=chart,
    )

# --- CRUD DE USUÁRIOS ---
@admin_bp.route('/admin/usuarios')
@admin_required
@login_required
def usuarios():
    q = (request.args.get("q") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()

    query = User.query
    if q:
        query = query.filter(
            db.or_(
                db.func.lower(User.nome).like(f"%{q}%"),
                db.func.lower(User.email).like(f"%{q}%"),
            )
        )

    if status == "ativos":
        query = query.filter(User.is_active.is_(True))
    elif status == "inativos":
        query = query.filter(User.is_active.is_(False))

    todos_usuarios = query.order_by(User.created_at.desc()).all()
    return render_template("admin/usuarios.html", usuarios=todos_usuarios, q=q, status=status)

@admin_bp.route('/admin/usuario/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
@login_required
def editar_usuario(id):
    usuario = User.query.get_or_404(id)
    if request.method == 'POST':
        usuario.nome = request.form.get('nome')
        usuario.email = request.form.get('email')
        usuario.categoria = request.form.get('categoria')
        usuario.is_active = request.form.get("is_active") == "1"
        
        # AJUSTE DE SEGURANÇA: Se for o e-mail master, força is_admin como verdadeiro
        if usuario.email.lower() in ADMIN_EMAILS:
            usuario.is_admin = True
        else:
            usuario.is_admin = request.form.get("is_admin") == "1"
            
        db.session.commit()
        flash(t_flash("Usuário atualizado!"), "sucesso")
        return redirect(url_for('admin.usuarios'))
    return render_template("admin/editar_usuario.html", u=usuario)

@admin_bp.route('/admin/usuario/deletar/<int:id>')
@admin_required
@login_required
def deletar_usuario(id):
    usuario = User.query.get_or_404(id)
    if usuario.email.lower() in ADMIN_EMAILS:
        flash(t_flash("Você não pode deletar a si mesma!"), "erro")
    else:
        db.session.delete(usuario)
        db.session.commit()
        flash(t_flash("Usuário removido com sucesso."), "sucesso")
    return redirect(url_for('admin.usuarios'))


@admin_bp.route("/admin/usuario/toggle-ativo/<int:id>")
@admin_required
@login_required
def toggle_usuario_ativo(id: int):
    usuario = User.query.get_or_404(id)
    if usuario.email.lower() in ADMIN_EMAILS:
        flash(t_flash("Você não pode desativar a conta master."), "erro")
        return redirect(url_for("admin.usuarios"))
    usuario.is_active = not bool(usuario.is_active)
    db.session.commit()
    flash(t_flash("Status do usuário updated."), "sucesso")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/admin/usuario/toggle-admin/<int:id>")
@admin_required
@login_required
def toggle_usuario_admin(id: int):
    usuario = User.query.get_or_404(id)
    if usuario.email.lower() in ADMIN_EMAILS:
        flash(t_flash("A conta master sempre permanece admin."), "info")
        return redirect(url_for("admin.usuarios"))
    usuario.is_admin = not bool(usuario.is_admin)
    db.session.commit()
    flash(t_flash("Permissão administrativa atualizada."), "sucesso")
    return redirect(url_for("admin.usuarios"))


# --- IMÓVEIS ---
@admin_bp.route("/admin/imoveis")
@admin_required
@login_required
def imoveis():
    imoveis = Imovel.query.order_by(Imovel.created_at.desc()).all()
    return render_template("admin/imoveis.html", imoveis=imoveis)


@admin_bp.route("/admin/imovel/deletar/<int:id>")
@admin_required
@login_required
def deletar_imovel(id: int):
    imovel = Imovel.query.get_or_404(id)
    db.session.delete(imovel)
    db.session.commit()
    flash(t_flash("Imóvel removido."), "sucesso")
    return redirect(url_for("admin.imoveis"))


@admin_bp.route("/admin/usuario/alterar-role/<int:id>", methods=["POST"])
@admin_required
@login_required
def alterar_role_usuario(id):
    usuario = User.query.get_or_404(id)
    if usuario.email.lower() in ADMIN_EMAILS:
        flash(t_flash("A conta master não pode ter o cargo alterado."), "erro")
        return redirect(url_for("admin.usuarios"))

    nova_role = request.form.get("role")
    if nova_role == "admin":
        usuario.is_admin = True
    else:
        usuario.is_admin = False

    # CORREÇÃO ADICIONADA: Se por algum motivo o email for alterado no form para o master, força admin
    if usuario.email.lower() in ADMIN_EMAILS:
        usuario.is_admin = True

    db.session.commit()
    flash(t_flash("Cargo de %(nome)s updated.", nome=usuario.nome), "sucesso")
    return redirect(url_for("admin.usuarios"))


# --- FINANCEIRO ---
@admin_bp.route("/admin/financeiro")
@admin_required
@login_required
def financeiro():
    from app.models.financas import Financeiro
    from sqlalchemy import func

    registros = Financeiro.query.order_by(Financeiro.data_registro.desc()).all()

    faturamento_bruto = db.session.query(func.sum(Financeiro.bruto)).scalar() or 0
    faturamento_liquido = db.session.query(func.sum(Financeiro.liq_plat)).scalar() or 0
    total_registros = len(registros)
    total_usuarios_financas = db.session.query(func.count(func.distinct(Financeiro.user_id))).scalar() or 0

    from app.models import User
    for r in registros:
        r.usuario = db.session.get(User, r.user_id)

    return render_template(
        "admin/financeiro.html",
        registros=registros,
        faturamento_bruto=faturamento_bruto,
        faturamento_liquido=faturamento_liquido,
        total_registros=total_registros,
        total_usuarios_financas=total_usuarios_financas,
    )