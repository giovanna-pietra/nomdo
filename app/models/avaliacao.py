"""
app/models/avaliacao.py
Avaliação enviada pelo hóspede após a estadia (nota + comentário livre).
Uma por Estadia — o link de avaliação some do jeito de "já avaliado"
depois do primeiro envio.
"""

from app.extensions import db
from app.models.base import TimestampMixin


class Avaliacao(TimestampMixin, db.Model):
    __tablename__ = "avaliacoes"

    id = db.Column(db.Integer, primary_key=True)

    estadia_id = db.Column(
        db.Integer,
        db.ForeignKey("estadia.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    imovel_id = db.Column(
        db.Integer,
        db.ForeignKey("imoveis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nome_hospede = db.Column(db.String(200), nullable=True)
    nota         = db.Column(db.Integer, nullable=False)   # 1 a 5
    comentario   = db.Column(db.Text, nullable=True)

    estadia = db.relationship("Estadia", backref=db.backref("avaliacao", uselist=False))
    imovel  = db.relationship("Imovel", backref="avaliacoes", lazy="select")

    def __repr__(self):
        return f"<Avaliacao {self.nota}★ - imovel {self.imovel_id}>"
