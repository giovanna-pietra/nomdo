"""
app/models/push_subscription.py
Inscrições de notificação push do navegador (Web Push / VAPID).

Cada linha representa UM navegador/dispositivo inscrito (um usuário pode
ter várias — celular, notebook, outro navegador etc.). `endpoint` é o URL
único que o serviço de push do navegador (FCM, Mozilla, etc.) gera pra
essa inscrição; `p256dh`/`auth` são as chaves de criptografia da mensagem,
tudo devolvido pelo próprio navegador em `PushSubscription.toJSON()`.
"""

from app.extensions import db
from app.models.base import TimestampMixin


class PushSubscription(TimestampMixin, db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    endpoint = db.Column(db.String(512), unique=True, nullable=False, index=True)
    p256dh   = db.Column(db.String(255), nullable=False)
    auth     = db.Column(db.String(255), nullable=False)

    # Só informativo (ajuda a identificar "qual dispositivo é esse" se um
    # dia tivermos uma tela de gerenciar inscrições) — nunca usado pra lógica.
    user_agent = db.Column(db.String(255), nullable=True)

    user = db.relationship(
        "User", backref=db.backref("push_subscriptions", cascade="all, delete-orphan", lazy="select")
    )

    def to_subscription_info(self) -> dict:
        """Formato que o `pywebpush` espera em `subscription_info`."""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh,
                "auth": self.auth,
            },
        }

    def __repr__(self):
        return f"<PushSubscription user={self.user_id} endpoint={self.endpoint[:40]}...>"
