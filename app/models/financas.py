from datetime import datetime, date

from app.extensions import db
from app.models.base import TimestampMixin


class Financeiro(db.Model):
    __tablename__ = "financeiros"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    imovel = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=True)
    site = db.Column(db.String(120), nullable=True)

    # Descrição livre do lançamento manual unificado (ex: "Gorjeta do
    # hóspede", "Conserto do ar-condicionado"). Substitui a antiga
    # separação entre "Novo Registro" (receita) e "Nova Despesa Geral" —
    # agora é um único lançamento com valor com sinal (positivo = receita,
    # negativo = despesa) e essa descrição em texto livre.
    descricao = db.Column(db.String(255), nullable=True)

    entrada = db.Column(db.Date, nullable=True)
    saida = db.Column(db.Date, nullable=True)

    bruto = db.Column(db.Float, default=0)
    liq_plat = db.Column(db.Float, default=0)

    data_registro = db.Column(db.DateTime, default=datetime.utcnow)

    despesas = db.relationship(
        "FinanceiroDespesa",
        backref="financeiro",
        cascade="all, delete-orphan",
        lazy=True
    )


class FinanceiroDespesa(db.Model):
    __tablename__ = "financeiro_despesas"

    id = db.Column(db.Integer, primary_key=True)

    financeiro_id = db.Column(
        db.Integer,
        db.ForeignKey("financeiros.id"),
        nullable=False
    )

    # Campo unificado como 'nome' para consistência com o JS e route
    nome = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Float, default=0)


class DespesaGeral(TimestampMixin, db.Model):
    """
    Despesa do imóvel que NÃO está ligada a uma estadia específica
    (ex: IPTU, condomínio, seguro, manutenção mensal). Diferente das
    despesas de FinanceiroDespesa/ItemEstadia, que sempre pertencem a
    um lançamento/estadia pontual, esta entra direto no balanço do
    imóvel/mês em Finanças, sem precisar de uma reserva associada.
    """
    __tablename__ = "despesas_gerais"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    imovel_id = db.Column(
        db.Integer,
        db.ForeignKey("imoveis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nome      = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(60),  nullable=True)   # ex: IPTU, Condomínio, Manutenção, Seguro, Outro
    valor     = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    data      = db.Column(db.Date, nullable=False, default=date.today)
    observacoes = db.Column(db.String(255), nullable=True)

    imovel = db.relationship(
        "Imovel",
        backref=db.backref("despesas_gerais", cascade="all, delete-orphan", lazy="select"),
    )
