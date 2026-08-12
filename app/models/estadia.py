"""
app/models/estadia.py
Modelo da tabela estadia — associada a um Imovel, gerencia entradas e saídas
de hóspedes do ponto de vista do anfitrião.

ATENÇÃO: as FKs usam "imoveis" e "users" (plural) para bater com os
__tablename__ definidos em imovel.py e user.py deste projeto.
"""

from datetime import datetime
from app.extensions import db


class ItemEstadia(db.Model):
    __tablename__ = "item_estadia"

    id         = db.Column(db.Integer, primary_key=True)
    estadia_id = db.Column(
        db.Integer,
        db.ForeignKey("estadia.id", ondelete="CASCADE"),
        nullable=False,
    )
    descricao   = db.Column(db.String(200), nullable=False)
    valor_cents = db.Column(db.Integer, nullable=False, default=0)

    estadia = db.relationship("Estadia", back_populates="itens")

    @property
    def valor(self) -> float:
        return self.valor_cents / 100

    @valor.setter
    def valor(self, v: float):
        self.valor_cents = int(round(float(v) * 100))

    def to_dict(self):
        return {
            "id":        self.id,
            "descricao": self.descricao,
            "valor":     f"{self.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "valor_raw": self.valor,
        }


class Estadia(db.Model):
    __tablename__ = "estadia"

    id        = db.Column(db.Integer, primary_key=True)
    imovel_id = db.Column(
        db.Integer,
        db.ForeignKey("imoveis.id", ondelete="CASCADE"),   # plural — bate com Imovel.__tablename__
        nullable=False,
    )
    user_id   = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),     # plural — bate com User.__tablename__
        nullable=False,
    )

    # Hóspede
    nome_hospede  = db.Column(db.String(200), nullable=False)
    email_hospede = db.Column(db.String(120), nullable=True)
    canal         = db.Column(db.String(50),  nullable=False, default="Direto")
    perfil        = db.Column(db.String(30),  nullable=False, default="Novo")
    qtd_hospedes  = db.Column(db.Integer,     nullable=False, default=1)

    # E-mails automáticos ao hóspede (guia pré-estadia / pedido de avaliação)
    email_guia_enviado      = db.Column(db.Boolean, nullable=False, default=False)
    email_avaliacao_enviado = db.Column(db.Boolean, nullable=False, default=False)
    token_avaliacao         = db.Column(db.String(64), unique=True, nullable=True, index=True)

    # Notificação push ao anfitrião avisando que o check-in é hoje — flag
    # de idempotência (mesmo padrão de email_guia_enviado), pra não mandar
    # duas vezes se o cron rodar mais de uma vez no mesmo dia.
    push_checkin_enviado = db.Column(db.Boolean, nullable=False, default=False)

    # Datas
    data_checkin    = db.Column(db.Date,      nullable=False)
    hora_checkin    = db.Column(db.String(5), nullable=False, default="14:00")
    data_checkout   = db.Column(db.Date,      nullable=False)
    hora_checkout   = db.Column(db.String(5), nullable=False, default="11:00")
    quantidade_dias = db.Column(db.Integer,   nullable=False, default=1)

    # Financeiro (em centavos para evitar float impreciso)
    moeda               = db.Column(db.String(5),   nullable=False, default="BRL")
    valor_bruto_cents   = db.Column(db.Integer,     nullable=False, default=0)
    valor_liquido_cents = db.Column(db.Integer,     nullable=True,  default=0)

    # Logística
    tem_carro   = db.Column(db.String(3),   nullable=False, default="Nao")
    tem_pet     = db.Column(db.String(3),   nullable=False, default="Nao")
    detalhe_pet = db.Column(db.String(200), nullable=True)

    # Status: confirmada | em_andamento | concluida | cancelada | bloqueio
    status    = db.Column(db.String(20), nullable=False, default="confirmada")
    criado_em = db.Column(db.DateTime,  default=datetime.utcnow)

    # Progresso do checklist de hospedagem (antes do check-in / depois do
    # check-out) específico desta estadia. JSON: {"antes:Testar wifi": true, ...}
    # A lista de itens em si vem do template do Imovel (checklist_itens) —
    # aqui só fica guardado o que já foi marcado como feito nesta estadia.
    checklist_status = db.Column(db.Text, nullable=True)

    # Relacionamentos
    imovel = db.relationship(
        "Imovel",
        backref=db.backref("estadia_list", lazy="dynamic")
    )
    itens = db.relationship(
        "ItemEstadia",
        back_populates="estadia",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Propriedades monetárias
    # ------------------------------------------------------------------
    @property
    def valor_bruto(self) -> float:
        return self.valor_bruto_cents / 100

    @valor_bruto.setter
    def valor_bruto(self, v: float):
        self.valor_bruto_cents = int(round(float(v) * 100))

    @property
    def valor_liquido(self) -> float:
        return (self.valor_liquido_cents or 0) / 100

    @valor_liquido.setter
    def valor_liquido(self, v: float):
        self.valor_liquido_cents = int(round(float(v) * 100))

    def total_itens(self) -> float:
        return sum(i.valor for i in self.itens)

    # ------------------------------------------------------------------
    # Formatação BR
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_brl(valor: float) -> str:
        s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "imovel_id":        self.imovel_id,
            "nome_hospede":     self.nome_hospede,
            "email_hospede":    self.email_hospede or "",
            "canal":            self.canal,
            "perfil":           self.perfil,
            "qtd_hospedes":     self.qtd_hospedes,
            "data_checkin":     self.data_checkin.isoformat()  if self.data_checkin  else "",
            "hora_checkin":     self.hora_checkin,
            "data_checkout":    self.data_checkout.isoformat() if self.data_checkout else "",
            "hora_checkout":    self.hora_checkout,
            "quantidade_dias":  self.quantidade_dias,
            "moeda":            self.moeda,
            "valor_bruto":      self.valor_bruto,
            "valor_bruto_fmt":  self._fmt_brl(self.valor_bruto),
            "valor_liquido":    self.valor_liquido,
            "valor_liquido_fmt":self._fmt_brl(self.valor_liquido),
            "total_itens":      self.total_itens(),
            "total_itens_fmt":  self._fmt_brl(self.total_itens()),
            "tem_carro":        self.tem_carro,
            "tem_pet":          self.tem_pet,
            "detalhe_pet":      self.detalhe_pet or "",
            "status":           self.status,
            "itens":            [i.to_dict() for i in self.itens],
            # campos para o FullCalendar
            "title":            self.nome_hospede,
            "start":            self.data_checkin.isoformat()  if self.data_checkin  else "",
            "end":              self.data_checkout.isoformat() if self.data_checkout else "",
        }