from .auth         import auth_bp
from .main         import main_bp
from .usuario      import usuario_bp
from .imoveis      import imoveis_bp
from .reservas     import reservas_bp
from .estadias     import estadias_bp
from .suporte      import suporte_bp
from .admin        import admin_bp
from .guia_publico import guia_publico_bp
from .hub          import hub_bp
from .cron         import cron_bp
from .pagamento    import pagamento_bp
from .documentos   import documentos_bp
from .equipe       import equipe_bp
from .api          import api_bp
from .push         import push_bp

from .pg_limpezas              import limpezas_bp
from .pg_manutencoes           import manutencoes_bp
from .pg_tarefas               import tarefas_bp
from .pg_checklists            import checklists_bp
from .pg_documentos_recebidos  import documentos_recebidos_bp
from .pg_rotinas               import rotinas_bp
from .pg_precificacao          import precificacao_bp

__all__ = [
    "auth_bp",
    "main_bp",
    "usuario_bp",
    "imoveis_bp",
    "reservas_bp",
    "estadias_bp",
    "suporte_bp",
    "admin_bp",
    "guia_publico_bp",
    "hub_bp",
    "cron_bp",
    "pagamento_bp",
    "documentos_bp",
    "equipe_bp",
    "api_bp",
    "push_bp",
    "limpezas_bp",
    "manutencoes_bp",
    "tarefas_bp",
    "checklists_bp",
    "documentos_recebidos_bp",
    "rotinas_bp",
    "precificacao_bp",
]