"""
app/models/__init__.py
Exporta todos os modelos para que o Flask-Migrate os descubra automaticamente.
"""

from .user    import User
from .imovel  import Grupo, Imovel
from .estadia import Estadia, ItemEstadia
from .financas import Financeiro, FinanceiroDespesa, DespesaGeral
from .hub     import HubTarefa, LembreteConfig
from .avaliacao import Avaliacao
from .precificacao import EventoPrecificacao
from .assinatura import Assinatura
from .pagamento import Pagamento
from .documentos import FormularioDocumentos
from .convite_anfitriao import ConviteAnfitriao
from .push_subscription import PushSubscription

__all__ = [
    "User",
    "Grupo",
    "Imovel",
    "Estadia",
    "ItemEstadia",
    "Financeiro",
    "FinanceiroDespesa",
    "DespesaGeral",
    "HubTarefa",
    "LembreteConfig",
    "Avaliacao",
    "EventoPrecificacao",
    "Pagamento",
    "Assinatura",
    "ConviteAnfitriao",
    "FormularioDocumentos",
    "PushSubscription",
]