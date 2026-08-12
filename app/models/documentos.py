"""
app/models/documentos.py
Formulário de Documentos do Hóspede — genérico e customizável pelo
anfitrião. Cada imóvel define, em
Imovel.documentos_campos, quais documentos/dados quer pedir (ex: RG/CPF,
placa do carro, foto do pet) e esse formulário guarda as respostas do
hóspede pra cada estadia — um link (token) por estadia, expirável.
"""
from __future__ import annotations

import json

from app.extensions import db
from app.models.base import TimestampMixin


class FormularioDocumentos(TimestampMixin, db.Model):
    __tablename__ = "formularios_documentos"

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

    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # pendente | respondido
    status = db.Column(db.String(20), nullable=False, default="pendente", index=True)
    tentativas_envio  = db.Column(db.Integer, nullable=False, default=0)
    data_ultimo_envio = db.Column(db.Date, nullable=True)
    respondido_em     = db.Column(db.DateTime, nullable=True)

    # Data limite pra acessar/preencher o link (checkout da estadia + alguns
    # dias de tolerância — ver DIAS_EXPIRA_APOS_CHECKOUT em documentos_service.py).
    expira_em = db.Column(db.Date, nullable=True)

    # ── Respostas do hóspede ──────────────────────────────────────
    # Espelha Imovel.documentos_campos no momento do envio, com o valor
    # preenchido: [{"nome":"RG/CPF","tipo":"foto","obrigatorio":true,"valor":"abc123_rg.jpg"}]
    # Pra tipo "foto", valor é o nome do arquivo salvo (ver salvar_arquivo);
    # pra tipo "texto", valor é o texto digitado (ex: placa do carro).
    respostas_json = db.Column(db.Text, nullable=True)

    estadia = db.relationship(
        "Estadia", backref=db.backref("formulario_documentos", uselist=False)
    )
    imovel = db.relationship("Imovel", backref="formularios_documentos", lazy="select")

    # ── Helpers JSON ────────────────────────────────────────────────
    @property
    def respostas(self) -> list:
        try:
            return json.loads(self.respostas_json) if self.respostas_json else []
        except (TypeError, ValueError):
            return []

    @respostas.setter
    def respostas(self, valor: list):
        self.respostas_json = json.dumps(valor or [], ensure_ascii=False)

    def __repr__(self):
        return f"<FormularioDocumentos {self.id} estadia={self.estadia_id} status={self.status}>"
