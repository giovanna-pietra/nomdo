"""
app/models/imovel.py
"""
import uuid
from slugify import slugify
from app.extensions import db
from app.models.base import TimestampMixin


class Grupo(TimestampMixin, db.Model):
    __tablename__ = "grupos"

    id      = db.Column(db.Integer, primary_key=True)
    nome    = db.Column(db.String(100), nullable=False)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    imoveis = db.relationship("Imovel", backref="grupo", lazy="select")

    def __repr__(self):
        return f"<Grupo {self.nome}>"


class Imovel(TimestampMixin, db.Model):
    __tablename__ = "imoveis"

    id       = db.Column(db.Integer, primary_key=True)
    titulo   = db.Column(db.String(150), nullable=False)
    endereco = db.Column(db.String(255), nullable=False)
    # Referência livre (ex: "perto do Shopping X", "ao lado da praça") — usada
    # só pra ajudar na busca do imóvel na listagem, não entra no endereço formal.
    ponto_referencia = db.Column(db.String(255), nullable=True)

    # ── Cidade / estado (região) ──────────────────────────────
    # `cidade` guarda exatamente o que o campo de busca de cidade no
    # formulário já preenchia ("Cidade/UF" pra endereços do Brasil, ou
    # "Cidade, Estado, País" pra fora) — esse valor já era digitado/escolhido
    # há tempos, só não era salvo no banco. `estado` é a UF derivada dele
    # (só quando dá pra reconhecer, ex: "São Paulo/SP" -> "SP"), usada pra
    # cruzar com feriados estaduais e pra agrupar oportunidades de
    # precificação por região (ver app/services/precificacao.py) — assim um
    # feriado/evento nacional não aparece repetido uma vez por imóvel quando
    # vários imóveis ficam na mesma cidade.
    cidade = db.Column(db.String(120), nullable=True)
    estado = db.Column(db.String(2),  nullable=True)

    # Imóvel inativo (ex: em reforma) continua existindo com todo o
    # histórico/estadias, só fica visualmente esmaecido na listagem — não é
    # um "soft delete" nem bloqueia nada automaticamente em outras telas.
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    # ── Conteúdo ─────────────────────────────────────────────
    utensilios     = db.Column(db.Text)   # JSON string: '[{"nome":"Cafeteira","valor":"50,00"}]'
    regras         = db.Column(db.Text)   # JSON string: '[{"texto":"Não fumar","horario":"","multa":""}]'
    foto_principal = db.Column(db.String(255))

    # ── Acesso / segurança ────────────────────────────────────
    wifi_rede         = db.Column(db.String(120), nullable=True)
    wifi_senha        = db.Column(db.String(120), nullable=True)
    senha_fechadura   = db.Column(db.String(120), nullable=True)
    ultima_troca_pilha = db.Column(db.Date, nullable=True)

    # ── Contato do anfitrião (visível para o hóspede no guia) ──
    contato_telefone = db.Column(db.String(30),  nullable=True)
    contato_email    = db.Column(db.String(120), nullable=True)

    # ── E-mails automáticos ao hóspede ──────────────────────────
    email_guia_ativo           = db.Column(db.Boolean, nullable=False, default=True)
    email_guia_dias_antes      = db.Column(db.Integer, nullable=True, default=1)
    email_avaliacao_ativo      = db.Column(db.Boolean, nullable=False, default=True)
    email_avaliacao_dias_depois = db.Column(db.Integer, nullable=True, default=2)

    slug_publico      = db.Column(db.String(100), unique=True, nullable=True, index=True)

    # ── Geolocalização ────────────────────────────────────────
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)

    # ── Operacional ───────────────────────────────────────────
    checkin_padrao      = db.Column(db.String(5),  nullable=True, default="14:00")
    checkout_padrao     = db.Column(db.String(5),  nullable=True, default="11:00")
    diaria_base         = db.Column(db.Numeric(10, 2), nullable=True)
    taxa_limpeza_padrao = db.Column(db.Numeric(10, 2), nullable=True)
    capacidade_max      = db.Column(db.Integer, nullable=True)
    qtd_quartos         = db.Column(db.Integer, nullable=True)
    qtd_banheiros       = db.Column(db.Integer, nullable=True)
    qtd_camas           = db.Column(db.Integer, nullable=True)

    # ── Política de cancelamento ──────────────────────────────
    prazo_cancelamento_gratis = db.Column(db.Integer, nullable=True)
    multa_tipo                = db.Column(db.String(20), nullable=True)   # sem_multa | percentual | fixo
    multa_valor               = db.Column(db.Numeric(10, 2), nullable=True)

    # NOTA: a feature de "Custos Fixos Mensais" (custo_manutencao_mensal,
    # custo_contas_mensal, contas_mensais) foi removida — as despesas
    # recorrentes flutuam mês a mês, então agora entram como um lançamento
    # normal de Despesa Geral em Finanças (ver DespesaGeral), que já é
    # somado dinamicamente no lucro do mês do Dashboard Proprietário.

    # ── Checklist de hospedagem (Hub do Anfitrião) ────────────
    # Modelo/template editável de itens de conferência antes do check-in e
    # depois do check-out. Se vazio, o Hub usa uma lista padrão (ver
    # DEFAULT_CHECKLIST_ITENS em app/routes/hub.py) — o anfitrião só precisa
    # mexer aqui se quiser personalizar os itens desse imóvel específico.
    checklist_itens = db.Column(db.Text, nullable=True)  # JSON: '[{"texto":"...","momento":"antes"}]'

    # ── Formulário de Documentos do Hóspede ───────────────────
    # Diferente do formulário do condomínio (fixo: pets/pessoas/placa, vai
    # pra portaria), este é um formulário genérico e customizável — cada
    # anfitrião define quais documentos/dados quer pedir (RG, CPF, foto do
    # pet, placa do carro etc). Enviado por e-mail antes do check-in com um
    # link expirável, um por estadia (ver FormularioDocumentos e
    # app/services/documentos_service.py). Se vazio, usa DEFAULT_CAMPOS_DOCUMENTOS.
    documentos_ativo      = db.Column(db.Boolean, nullable=False, default=False)
    documentos_dias_antes = db.Column(db.Integer, nullable=True, default=3)
    documentos_campos     = db.Column(db.Text, nullable=True)  # JSON: '[{"nome":"RG/CPF","tipo":"foto","obrigatorio":true}]'

    # ── FK ───────────────────────────────────────────────────
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grupo_id = db.Column(
        db.Integer,
        db.ForeignKey("grupos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Helpers / Métodos ─────────────────────────────────────
    def gerar_slug(self):
        """Gera um slug amigável e único baseado no título."""
        if self.titulo:
            slug_base = slugify(self.titulo)
            # Adiciona um sufixo curto aleatório para evitar colisões de links idênticos
            self.slug_publico = f"{slug_base}-{uuid.uuid4().hex[:6]}"

    def dias_desde_troca_pilha(self) -> int:
        from datetime import date
        if self.ultima_troca_pilha is None:
            return 999
        return (date.today() - self.ultima_troca_pilha).days

    def __repr__(self):
        return f"<Imovel {self.titulo}>"