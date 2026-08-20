"""
app/models/hub.py
Modelos do Hub do Anfitrião:

- HubTarefa       → item concreto de checklist/pendência (manutenção, limpeza,
                     troca de pilha, ou qualquer rotina customizada).
- LembreteConfig  → regra recorrente ("a cada N dias" ou disparada por evento,
                     como checkout de uma Estadia) que gera HubTarefas e
                     dispara e-mail para o anfitrião automaticamente.
"""

from datetime import date, timedelta

from app.extensions import db
from app.models.base import TimestampMixin


# Metadados de exibição/e-mail por tipo de lembrete — usados tanto no
# back-end (título padrão, e-mail) quanto exportados pro front (ícone/cor).
TIPOS_LEMBRETE = {
    "pilha_fechadura": {"icone": "🔋", "label": "Troca de Pilha da Fechadura", "cor": "#f59e0b"},
    "limpeza_checkout": {"icone": "🧹", "label": "Limpeza Pós-Checkout", "cor": "#16a34a"},
    "eletronicos": {"icone": "🔌", "label": "Checkup de Eletrônicos", "cor": "#2563eb"},
    "cafe": {"icone": "☕", "label": "Reposição de Cápsulas de Café", "cor": "#92400e"},
    "papel_higienico": {"icone": "🧻", "label": "Reposição de Papel Higiênico", "cor": "#0ea5e9"},
    "manutencao": {"icone": "🛠️", "label": "Manutenção", "cor": "#ea580c"},
    "comprar": {"icone": "🛒", "label": "Comprar algo", "cor": "#0891b2"},
    "repor": {"icone": "📦", "label": "Repor algo", "cor": "#65a30d"},
    "personalizado": {"icone": "📝", "label": "Tarefa Personalizada", "cor": "#64748b"},
    "checklist_antes": {"icone": "📋", "label": "Checklist de Entrada Pendente", "cor": "#7c3aed"},
    "checklist_depois": {"icone": "📋", "label": "Checklist de Saída Pendente", "cor": "#7c3aed"},
    "outro": {"icone": "📌", "label": "Lembrete Personalizado", "cor": "#7c3aed"},
}

# Tipos que são disparados por evento (não por contagem de dias).
TIPOS_EVENTO = {"limpeza_checkout", "checklist_antes", "checklist_depois"}


class HubTarefa(TimestampMixin, db.Model):
    __tablename__ = "hub_tarefas"

    id        = db.Column(db.Integer, primary_key=True)

    user_id   = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    imovel_id = db.Column(
        db.Integer,
        db.ForeignKey("imoveis.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    estadia_id = db.Column(
        db.Integer,
        db.ForeignKey("estadia.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lembrete_config_id = db.Column(
        db.Integer,
        db.ForeignKey("lembrete_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Autoria — quem de fato registrou/concluiu a tarefa (diferente de
    # `user_id`, que é sempre o Proprietário "dono" dos dados — ver
    # get_effective_owner_id). Útil numa equipe com mais de uma pessoa
    # (Proprietário + Anfitriões-ajudantes) pra saber quem fez o quê.
    # Fica nulo em dois casos: tarefa gerada automaticamente pelo motor de
    # lembretes (processar_lembretes, sem ninguém "apertando o botão"), ou
    # registro antigo, de antes dessa coluna existir.
    criado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    concluido_por_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    titulo    = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)

    # "manutencao" | "limpeza_checkout" | "pilha_fechadura" | "eletronicos" |
    # "cafe" | "papel_higienico" | "outro"
    tipo      = db.Column(db.String(50), nullable=False, default="manutencao")

    # Data prevista/agendada pro item (opcional) — usada pelas tarefas
    # avulsas criadas manualmente na aba "Cuidados do Imóvel" (limpeza/
    # manutenção/comprar/repor/personalizado). Não confundir com
    # `created_at` (TimestampMixin), que é o momento do registro.
    data_prevista = db.Column(db.Date, nullable=True)

    concluida = db.Column(db.Boolean, nullable=False, default=False)

    # Se um e-mail já foi disparado para essa tarefa (evita reenvio duplicado
    # quando a página/API é recarregada várias vezes).
    email_enviado = db.Column(db.Boolean, nullable=False, default=False)

    # Relacionamento para pegar o nome do imóvel facilmente
    imovel    = db.relationship("Imovel", backref="tarefas", lazy="select")
    estadia   = db.relationship("Estadia", backref="tarefas_hub", lazy="select")

    # Sem backref pro lado do User (evita colidir com outros relacionamentos
    # já existentes em User) — só precisamos ler o nome de quem criou/concluiu.
    criado_por    = db.relationship("User", foreign_keys=[criado_por_id], lazy="select")
    concluido_por = db.relationship("User", foreign_keys=[concluido_por_id], lazy="select")

    def __repr__(self):
        return f"<HubTarefa {self.tipo}: {self.titulo}>"


class LembreteConfig(TimestampMixin, db.Model):
    """
    Regra de lembrete recorrente por imóvel. Duas famílias:

    - Por intervalo (`intervalo_dias` preenchido): ex. troca de pilha a cada
      20 dias, checkup de eletrônicos a cada 90 dias, café/papel higiênico
      a cada N dias — qualquer rotina customizada ("outro").
    - Por evento (`intervalo_dias` nulo, tipo em TIPOS_EVENTO): ex. limpeza
      pós-checkout, disparada automaticamente quando uma Estadia termina.
    """
    __tablename__ = "lembrete_configs"

    id      = db.Column(db.Integer, primary_key=True)

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

    tipo      = db.Column(db.String(30), nullable=False, default="outro")
    # Obrigatório apenas quando tipo == "outro"; nos demais tipos o label
    # padrão de TIPOS_LEMBRETE é usado se este campo ficar vazio.
    titulo    = db.Column(db.String(150), nullable=True)
    descricao = db.Column(db.Text, nullable=True)

    # Dias entre disparos. Nulo para lembretes disparados por evento.
    intervalo_dias = db.Column(db.Integer, nullable=True)

    ativo        = db.Column(db.Boolean, nullable=False, default=True)
    ultimo_envio = db.Column(db.Date, nullable=True)

    imovel = db.relationship("Imovel", backref="lembretes", lazy="select")

    # ── Helpers ────────────────────────────────────────────────
    def label(self) -> str:
        if self.titulo:
            return self.titulo
        return TIPOS_LEMBRETE.get(self.tipo, {}).get("label", "Lembrete")

    def proxima_data(self):
        """Data prevista do próximo disparo (None se for lembrete por evento)."""
        if not self.intervalo_dias:
            return None
        base = self.ultimo_envio or self.created_at.date()
        return base + timedelta(days=self.intervalo_dias)

    def dias_para_vencer(self):
        """Dias até o próximo disparo (negativo = já vencido). None se por evento."""
        prox = self.proxima_data()
        if prox is None:
            return None
        return (prox - date.today()).days

    def vencido(self) -> bool:
        dias = self.dias_para_vencer()
        return dias is not None and dias <= 0

    def __repr__(self):
        return f"<LembreteConfig {self.tipo}: {self.label()}>"