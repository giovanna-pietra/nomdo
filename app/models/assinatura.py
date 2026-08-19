"""
app/models/assinatura.py
Assinatura mensal recorrente via Asaas — substitui o antigo modelo de
"pagamento único pra sempre". O plano é definido pela quantidade de
imóveis do Proprietário (ver app/services/planos.py):

    até 5 imóveis   -> "ate_5"   -> R$ 20/mês
    até 10 imóveis  -> "ate_10"  -> R$ 35/mês
    11+ imóveis     -> "mais_10" -> R$ 50/mês

Cada Assinatura representa a inscrição na Asaas (1 por Proprietário —
ajudantes nunca têm a própria, ver User.owner_id/e_ajudante). Cada
cobrança gerada mensalmente pela assinatura continua virando uma linha
em Pagamento (agora com assinatura_id preenchido), então o histórico de
cobranças recebidas continua todo em Pagamento — só o "contrato" em si
(plano atual, próximo vencimento, status) é que mora aqui.

O status de acesso "oficial" do usuário continua em User.pagamento_ativo,
setado a partir do status desta Assinatura (ver app/routes/pagamento.py).
"""
from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin

# Mantidos como referência simples — a fonte da verdade de preço/limite
# vive em app/services/planos.py (PLANOS). Duplicar os nomes aqui só
# documenta os valores aceitos na coluna `plano`.
PLANOS_VALIDOS = ("ate_5", "ate_10", "mais_10")

# Status espelham o que a Asaas usa para assinatura (ACTIVE, EXPIRED,
# OVERDUE, INACTIVE), sempre em minúsculo aqui pra ficar consistente com
# o padrão já usado em Pagamento.status.
STATUS_VALIDOS = ("pending", "active", "overdue", "expired", "inactive", "canceled")


class Assinatura(TimestampMixin, db.Model):
    __tablename__ = "assinaturas"

    id = db.Column(db.Integer, primary_key=True)

    # Sempre o id do Proprietário (User.owner_id) — nunca de um ajudante.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    asaas_subscription_id = db.Column(db.String(60), nullable=True, unique=True, index=True)

    plano = db.Column(db.String(20), nullable=False, default="ate_5")
    valor_cents = db.Column(db.Integer, nullable=False, default=0)
    ciclo = db.Column(db.String(20), nullable=False, default="MONTHLY")

    # pending | active | overdue | expired | inactive | canceled
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)

    proximo_vencimento = db.Column(db.Date, nullable=True)
    cancelado_em = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="assinaturas")

    @property
    def valor(self) -> float:
        return (self.valor_cents or 0) / 100

    @property
    def ativa(self) -> bool:
        return self.status in ("active", "overdue")

    def __repr__(self):
        return f"<Assinatura {self.id} user={self.user_id} plano={self.plano} status={self.status}>"
