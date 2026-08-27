"""
app/models/user.py
Modelo de usuário com índices e relacionamentos profissionais.
"""

from app.extensions import db
from app.models.base import TimestampMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id   = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf  = db.Column(db.String(14), unique=True, nullable=True)

    # ── Paywall (Asaas) ───────────────────────────────────────
    # pagamento_ativo = já pagou o acesso (pagamento único, "para sempre").
    # Donos/admins (ver ADMIN_EMAILS em auth.py) nunca precisam pagar —
    # o gate global em app/__init__.py já libera quem é is_admin.
    pagamento_ativo   = db.Column(db.Boolean, default=False, nullable=False)
    asaas_customer_id = db.Column(db.String(60), nullable=True)

    email = db.Column(db.String(120), unique=True, nullable=False, index=True)

    telefone  = db.Column(db.String(20))
    categoria = db.Column(db.String(50))

    # Flags administrativas / segurança
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
    last_login_at = db.Column(db.DateTime)

    # Preferências do usuário (Configurações)
    theme = db.Column(db.String(10), nullable=False, default="light")
    language = db.Column(db.String(10), nullable=False, default="pt-br")
    currency = db.Column(db.String(5), nullable=False, default="BRL")
    # Navegador começa DESLIGADO por padrão: ligar de verdade depende de
    # pedir permissão ao usuário (só rola com um gesto/clique dele), então
    # não faz sentido nascer "true" sem essa permissão sequer ter sido
    # concedida. E-mail não tem essa dependência, então começa ligado.
    notify_browser = db.Column(db.Boolean, nullable=False, default=False)
    notify_email = db.Column(db.Boolean, nullable=False, default=True)

    # Percentuais de aumento sugerido no sistema de precificação do Hub
    # (por nível de impacto). Nulo = usa o padrão do sistema (30/15/5%).
    pct_precificacao_alta  = db.Column(db.Integer, nullable=True)
    pct_precificacao_media = db.Column(db.Integer, nullable=True)
    pct_precificacao_baixa = db.Column(db.Integer, nullable=True)

    # Armazenado como hash — NUNCA em texto puro
    _senha = db.Column("senha", db.String(255), nullable=False, default="")

    genero           = db.Column(db.String(20))
    data_nascimento  = db.Column(db.Date)

    is_confirmed       = db.Column(db.Boolean, default=False, nullable=False)
    codigo_verificacao = db.Column(db.String(6))

    auth_provider = db.Column(db.String(20), default="email", nullable=False)
    foto          = db.Column(db.String(255))

    papel = db.Column(db.String(20), default="Usuário", nullable=True, index=True)

    # ── Hierarquia Proprietário / Anfitrião-ajudante ──────────
    # NULL = conta independente (é Proprietário-e-Anfitrião de si mesma —
    #        continua funcionando exatamente como antes).
    # preenchido = conta de "Anfitrião-ajudante": não é dona de nada, opera
    #        por conta do Proprietário apontado aqui (convidada por e-mail;
    #        ver ConviteAnfitriao). Um ajudante só pode estar vinculado a
    #        UM Proprietário por vez.
    proprietario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Relacionamentos ──────────────────────────────────────
    grupos = db.relationship(
        "Grupo", backref="usuario", lazy="select", cascade="all, delete-orphan"
    )
    imoveis = db.relationship(
        "Imovel", backref="proprietario", lazy="select", cascade="all, delete-orphan"
    )
    # Do lado do Proprietário: lista de contas de Anfitrião-ajudante vinculadas.
    # Do lado do ajudante: `conta_proprietario` dá a conta do Proprietário.
    anfitrioes_vinculados = db.relationship(
        "User",
        backref=db.backref("conta_proprietario", remote_side=[id]),
        foreign_keys=[proprietario_id],
        lazy="select",
    )

    # ── Hierarquia: helpers ───────────────────────────────────
    @property
    def owner_id(self) -> int:
        """
        ID efetivo do "dono" das informações (imóveis, estadias,
        financeiro, hub, precificação, pagamento) para esta conta.
        Contas independentes retornam o próprio id; contas de
        Anfitrião-ajudante retornam o id do Proprietário vinculado.
        Use isto (em vez de user.id) em toda query que escopa dados por
        conta — assim um ajudante enxerga/opera nos dados do Proprietário
        em vez de numa conta própria vazia.
        """
        return self.proprietario_id or self.id

    @property
    def e_ajudante(self) -> bool:
        """True se esta conta é um Anfitrião-ajudante ou Auxiliar (trabalha para outra conta)."""
        return self.proprietario_id is not None

    @property
    def e_auxiliar(self) -> bool:
        """
        True só para o tipo de ajudante mais restrito: Auxiliar. Não tem
        acesso a NENHUM dado (sem estadias, hóspedes, finanças, imóveis) —
        só executa tarefas operacionais do Hub (limpeza/manutenção e o
        checklist de condição do imóvel). Ver gate_auxiliar_acesso() em
        app/__init__.py, que é quem realmente impõe essa restrição em
        toda rota da aplicação.
        """
        return self.e_ajudante and self.categoria == "Auxiliar"

    # ── Senha helpers ────────────────────────────────────────
    @property
    def senha(self):
        raise AttributeError("Leia o hash via _senha; não exponha a senha direta.")

    @senha.setter
    def senha(self, plaintext: str):
        if plaintext:
            self._senha = generate_password_hash(plaintext)

    def verificar_senha(self, plaintext: str) -> bool:
        if not self._senha:
            return False
        return check_password_hash(self._senha, plaintext)

    def __repr__(self):
        return f"<User {self.email}>"
