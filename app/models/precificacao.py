"""
app/models/precificacao.py
Eventos personalizados cadastrados pelo anfitrião (show, festival,
temporada local etc.) usados pelo motor de precificação do Hub junto com
os feriados nacionais calculados em app/services/feriados.py.
"""

from app.extensions import db
from app.models.base import TimestampMixin

# Nível de impacto → usado para escolher o percentual de aumento sugerido.
NIVEIS_IMPACTO = {
    "alta":  {"label": "Alta demanda",  "cor": "#dc2626"},
    "media": {"label": "Média demanda", "cor": "#f59e0b"},
    "baixa": {"label": "Baixa demanda", "cor": "#0ea5e9"},
}

# Percentuais padrão de aumento sugerido, usados quando o anfitrião não
# configurou valores próprios em User.
PCT_PADRAO = {
    "alta":  30,
    "media": 15,
    "baixa": 5,
}


class EventoPrecificacao(TimestampMixin, db.Model):
    __tablename__ = "eventos_precificacao"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nulo = aplica a todos os imóveis do anfitrião.
    imovel_id = db.Column(
        db.Integer,
        db.ForeignKey("imoveis.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    titulo = db.Column(db.String(150), nullable=False)
    data = db.Column(db.Date, nullable=False)

    # Se marcado, o evento é recalculado todo ano para a mesma data
    # (dia/mês), útil para réveillon local, festival anual, etc.
    recorrente = db.Column(db.Boolean, nullable=False, default=False)

    nivel_impacto = db.Column(db.String(10), nullable=False, default="media")

    imovel = db.relationship("Imovel", backref="eventos_precificacao", lazy="select")

    def __repr__(self):
        return f"<EventoPrecificacao {self.titulo} - {self.data}>"
