"""
app/models/convite_anfitriao.py
Convite enviado por um Proprietário para vincular uma conta de
Anfitrião-ajudante (que passa a operar sobre os imóveis do Proprietário).
"""
import secrets
from datetime import datetime, timedelta

from app.extensions import db
from app.models.base import TimestampMixin


class ConviteAnfitriao(TimestampMixin, db.Model):
    __tablename__ = "convites_anfitriao"

    id = db.Column(db.Integer, primary_key=True)

    proprietario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email = db.Column(db.String(120), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # pendente | aceito | cancelado
    status = db.Column(db.String(20), nullable=False, default="pendente")

    aceito_em = db.Column(db.DateTime, nullable=True)
    # Conta que efetivamente aceitou (pode diferir do e-mail digitado, se a
    # pessoa criar a conta com outro e-mail confirmado — na prática vamos
    # sempre exigir o mesmo e-mail, mas guardamos o vínculo explicitamente).
    anfitriao_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    proprietario = db.relationship("User", foreign_keys=[proprietario_id])
    anfitriao    = db.relationship("User", foreign_keys=[anfitriao_id])

    @staticmethod
    def gerar_token() -> str:
        return secrets.token_urlsafe(32)

    def expirado(self, dias: int = 7) -> bool:
        return datetime.utcnow() - self.created_at > timedelta(days=dias)

    def __repr__(self):
        return f"<ConviteAnfitriao {self.email} ({self.status})>"
