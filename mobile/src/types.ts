// Tipos espelhando exatamente o JSON devolvido por app/routes/api.py.

export interface Usuario {
  id: number;
  nome: string;
  email: string;
  categoria: string | null;
  papel: string | null;
  is_admin: boolean;
  e_ajudante: boolean;
  foto: string | null;
  theme: string | null;
}

export interface Perfil {
  id: number;
  nome: string;
  email: string;
  telefone: string | null;
  genero: string | null;
  data_nascimento: string | null;
  categoria: string | null;
  e_ajudante: boolean;
  foto: string | null;
  theme: string | null;
  language: string | null;
  currency: string | null;
  notify_browser: boolean;
  notify_email: boolean;
}

export interface Imovel {
  id: number;
  titulo: string;
  endereco: string;
  ponto_referencia: string | null;
  grupo_id: number | null;
  pattern: number;
  foto_principal: string | null;
  cidade: string | null;
  estado: string | null;
  wifi_rede: string | null;
  wifi_senha: string | null;
  senha_fechadura: string | null;
  contato_telefone: string | null;
  contato_email: string | null;
  checkin_padrao: string | null;
  checkout_padrao: string | null;
  diaria_base: number | null;
  taxa_limpeza_padrao: number | null;
  capacidade_max: number | null;
  qtd_quartos: number | null;
  qtd_banheiros: number | null;
  qtd_camas: number | null;
  slug_publico: string | null;
}

export interface Grupo {
  id: number;
  nome: string;
  imovel_ids: number[];
  imoveis_count: number;
}

export interface DashboardStats {
  total_imoveis: number;
  reservas_ativas: number;
  checkins_hoje: number;
  faturamento_total: string;
  media_ocupacao: number;
  imovel_mais_procurado: string;
  imovel_menos_procurado: string;
  revpar: string;
}

export interface DashboardResponse {
  tem_imoveis: boolean;
  tem_estadias: boolean;
  dashboard_desbloqueado: boolean;
  stats: DashboardStats;
  faturamento_chart: { labels: string[]; values: number[] };
  estadias_chart: { labels: string[]; values: number[] };
}

export interface DespesaItem {
  nome: string;
  valor: number;
}

export interface LancamentoFinanceiro {
  id: number;
  tipo: "manual" | "estadia" | "despesa_geral";
  editavel: boolean;
  imovel_id?: number | null;
  imovel: string;
  status: string | null;
  site: string | null;
  entrada: string;
  saida: string;
  bruto: number;
  liqPlat: number;
  data: string;
  categoria?: string;
  observacoes?: string | null;
  despesas: DespesaItem[];
}

export interface FinancasResponse {
  imoveis: { id: number; titulo: string }[];
  lancamentos: LancamentoFinanceiro[];
}

export interface HubImovelScore {
  id: number;
  titulo: string;
  score: number;
  nivel: "excelente" | "atencao" | "critico";
  alertas: string[];
  dias_pilha: number | null;
  foto_principal: string | null;
}

export interface HubTarefaItem {
  id: number;
  titulo: string;
  descricao: string | null;
  tipo: string;
  tipo_label: string;
  tipo_icone: string;
  tipo_cor: string;
  imovel_id: number | null;
  imovel: string;
  criado_em: string;
  data_prevista: string | null;
  data_prevista_fmt: string | null;
}

export interface HubResponse {
  total_imoveis: number;
  manutencoes_abertas: number;
  limpezas_pendentes: number;
  pilhas_vencidas: number;
  tarefas_pendentes_total: number;
  proximo_checkin: {
    quando: string;
    hora: string | null;
    hospede: string;
    imovel: string;
  } | null;
  imoveis: HubImovelScore[];
  tarefas: HubTarefaItem[];
}

export interface AnfitriaoEquipe {
  id: number;
  nome: string;
  email: string;
  foto: string | null;
}

export interface ConviteEquipe {
  id: number;
  email: string;
  status: string;
  criado_em: string;
  expirado: boolean;
}

export interface EquipeResponse {
  anfitrioes: AnfitriaoEquipe[];
  convites_pendentes: ConviteEquipe[];
}

export interface ImovelLucro {
  id: number;
  titulo: string;
  foto_principal: string | null;
  faturamento_mes: number;
  despesas_mes: number;
  lucro_mes: number;
  faturamento_total: number;
  despesas_total: number;
  lucro_total: number;
}

export interface ProprietarioResponse {
  imoveis: ImovelLucro[];
  consolidado: {
    faturamento_mes: number;
    despesas_mes: number;
    lucro_mes: number;
    faturamento_total: number;
    despesas_total: number;
    lucro_total: number;
  };
  mes_referencia: string;
  tem_imoveis: boolean;
  tem_estadias: boolean;
}

export interface AdminUsuario {
  id: number;
  nome: string;
  email: string;
  categoria: string | null;
  is_active: boolean;
  is_admin: boolean;
  criado_em: string;
}

export interface AdminImovel {
  id: number;
  titulo: string;
  endereco: string;
  foto_principal: string | null;
  user_id: number;
  proprietario: string;
  criado_em: string;
}

export interface AdminDashboardResponse {
  stats: {
    total_usuarios: number;
    usuarios_ativos: number;
    usuarios_admin: number;
    novos_mes: number;
    novos_30d: number;
    total_imoveis: number;
    total_estadias: number;
    faturamento: string;
    ocupacao: number;
  };
  usuarios_recentes: AdminUsuario[];
  chart: {
    labels: string[];
    users_by_month: number[];
    estadias_by_month: number[];
  };
}

export interface AdminFinanceiroRegistro {
  id: number;
  imovel: string | null;
  usuario: string;
  site: string | null;
  status: string | null;
  bruto: number;
  liqPlat: number;
  data: string;
}

export interface AdminFinanceiroResponse {
  registros: AdminFinanceiroRegistro[];
  faturamento_bruto: number;
  faturamento_liquido: number;
  total_registros: number;
  total_usuarios_financas: number;
}
