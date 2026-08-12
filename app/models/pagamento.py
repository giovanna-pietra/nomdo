"""
app/models/pagamento.py
Registro de cobranças via Asaas. Historicamente era só o pagamento único
("comprar o acesso pra sempre"); agora que o acesso virou assinatura
mensal (ver app/models/assinatura.py), cada linha aqui pode ser tanto uma
cobrança avulsa antiga quanto uma das cobranças mensais geradas
automaticamente por uma Assinatura (nesse caso `assinatura_id` é
preenchido). O status de acesso "oficial" do usuário fica em
User.pagamento_ativo, setado a partir do status da Assinatura/cobrança
confirmada (ver app/routes/pagamento.py).
"""
from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin


class Pagamento(TimestampMixin, db.Model):
    __tablename__ = "pagamentos"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    asaas_customer_id = db.Column(db.String(60), nullable=True)
    asaas_payment_id  = db.Column(db.String(60), nullable=True, unique=True, index=True)

    # Preenchido quando esta cobrança foi gerada automaticamente por uma
    # assinatura mensal (nulo nas cobranças avulsas antigas).
    assinatura_id = db.Column(
        db.Integer,
        db.ForeignKey("assinaturas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    valor_cents  = db.Column(db.Integer, nullable=False, default=0)
    billing_type = db.Column(db.String(20), nullable=True)   # PIX | BOLETO | CREDIT_CARD | UNDEFINED

    invoice_url = db.Column(db.String(255), nullable=True)

    # pending | confirmed | received | overdue | failed | refunded
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    confirmado_em = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="pagamentos")
    assinatura = db.relationship("Assinatura", backref="cobrancas")

    @property
    def valor(self) -> float:
        return (self.valor_cents or 0) / 100

    def __repr__(self):
        return f"<Pagamento {self.id} user={self.user_id} status={self.status}>"
