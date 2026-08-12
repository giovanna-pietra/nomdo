"""
app/utils/auth.py
Decorators de autenticação e helpers de sessão.
"""

from functools import wraps
from flask import flash, request, session, redirect, url_for

def usuario_logado() -> bool:
    return "user_id" in session


def get_effective_owner_id():
    """
    Retorna o ID efetivo do "dono" das informações (imóveis, estadias,
    financeiro, hub, precificação, pagamento) para a sessão atual.

    Se a conta logada for um Anfitrião-ajudante (User.proprietario_id
    preenchido), retorna o ID do Proprietário ao qual está vinculada — assim
    o ajudante enxerga/opera nos dados do Proprietário em vez de numa conta
    própria vazia. Contas independentes (proprietario_id nulo) recebem o
    próprio ID, exatamente como antes da hierarquia Proprietário/Anfitrião.

    Use isto (ou a property equivalente `User.owner_id`, quando você já tem
    o objeto User em mãos) em toda query que hoje faz
    `filter_by(user_id=session["user_id"])`.
    """
    from app.models import User
    from app.extensions import db

    user_id = session.get("user_id")
    if not user_id:
        return None

    user = db.session.get(User, user_id)
    if not user:
        return None

    return user.owner_id


def login_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            flash("Sua sessão expirou.", "aviso")
            return redirect(
                url_for("auth.login")
            )

        # Usuário desativado (admin)
        try:
            from app.models import User
            from app.extensions import db
            user = db.session.get(User, session.get("user_id"))
            if not user or (hasattr(user, "is_active") and not user.is_active):
                session.clear()
                flash("Sua conta está desativada.", "erro")
                return redirect(url_for("auth.login"))
        except Exception:
            # Não bloqueia request se houver falha transitória de DB
            pass

        return func(*args, **kwargs)

    return wrapper


def confirmar_conta_required(func):
    """Exige que a conta do usuário esteja confirmada por e-mail."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        from app.models import User
        user = User.query.get(session.get("user_id"))
        if not user or not user.is_confirmed:
            from flask import flash
            flash("Confirme seu e-mail antes de acessar esta área.", "erro")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    return wrapper
