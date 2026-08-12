import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Modal,
  TextInput,
  Alert,
  ScrollView,
} from "react-native";
import { Picker } from "@react-native-picker/picker";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { FinancasResponse, LancamentoFinanceiro } from "../types";
import { cores, raio, sombraCard } from "../theme";

// Espelha app/templates/financas.html ("Gestão Financeira" / "Fluxo de
// Caixa"): 6 KPIs (Lucro Líquido, Taxas+Despesas, Faturamento Bruto,
// Margem de Lucro, Registros, Melhor Site), busca/filtros e o fluxo de
// "Novo Lançamento" (POST /api/financas) + despesa geral rápida.
const CATEGORIAS_DESPESA = ["IPTU", "Condomínio", "Manutenção", "Seguro", "Outro"];

function formatarMoeda(valor: number): string {
  return (valor || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Kpi({ label, valor, cor }: { label: string; valor: string; cor: string }) {
  return (
    <View style={styles.kpiCard}>
      <View style={[styles.kpiBarra, { backgroundColor: cor }]} />
      <Text style={styles.kpiLabel}>{label}</Text>
      <Text style={styles.kpiValor} numberOfLines={1}>{valor}</Text>
    </View>
  );
}

const TIPO_LABEL: Record<string, string> = {
  manual: "Manual",
  estadia: "Estadia",
  despesa_geral: "Despesa Geral",
};

export default function FinancasScreen() {
  const { token } = useAuth();
  const [dados, setDados] = useState<FinancasResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [busca, setBusca] = useState("");
  const [filtroImovel, setFiltroImovel] = useState("");
  const [filtroSite, setFiltroSite] = useState("");

  // Modal: Novo Lançamento (manual, igual ao "Fluxo de Caixa" do site)
  const [modalLancamento, setModalLancamento] = useState(false);
  const [lImovel, setLImovel] = useState("");
  const [lSite, setLSite] = useState("");
  const [lStatus, setLStatus] = useState("");
  const [lEntrada, setLEntrada] = useState("");
  const [lBruto, setLBruto] = useState("");
  const [lLiqPlat, setLLiqPlat] = useState("");
  const [lDespesas, setLDespesas] = useState<{ nome: string; valor: string }[]>([]);
  const [salvandoLancamento, setSalvandoLancamento] = useState(false);

  // Modal: Despesa Geral rápida (por categoria, ligada a um imóvel)
  const [modalDespesa, setModalDespesa] = useState(false);
  const [dImovelId, setDImovelId] = useState<number | null>(null);
  const [dCategoria, setDCategoria] = useState(CATEGORIAS_DESPESA[0]);
  const [dValor, setDValor] = useState("");
  const [salvandoDespesa, setSalvandoDespesa] = useState(false);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await apiFetch<FinancasResponse>("/api/financas", { token });
      setDados(resposta);
      if (!dImovelId && resposta.imoveis.length > 0) {
        setDImovelId(resposta.imoveis[0].id);
      }
      if (!lImovel && resposta.imoveis.length > 0) {
        setLImovel(resposta.imoveis[0].titulo);
      }
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar as finanças.");
    } finally {
      setCarregando(false);
      setAtualizando(false);
    }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    carregar();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const lancamentosFiltrados = useMemo(() => {
    let lista = dados?.lancamentos || [];
    if (filtroImovel) lista = lista.filter((l) => l.imovel === filtroImovel);
    if (filtroSite) lista = lista.filter((l) => (l.site || "") === filtroSite);
    if (busca.trim()) {
      const termo = busca.trim().toLowerCase();
      lista = lista.filter((l) => (l.imovel || "").toLowerCase().includes(termo));
    }
    return lista;
  }, [dados, filtroImovel, filtroSite, busca]);

  const sitesDisponiveis = useMemo(() => {
    const set = new Set<string>();
    (dados?.lancamentos || []).forEach((l) => l.site && set.add(l.site));
    return Array.from(set);
  }, [dados]);

  const kpis = useMemo(() => {
    const lancamentos = dados?.lancamentos || [];
    const faturamentoBruto = lancamentos.reduce((soma, l) => soma + (l.bruto || 0), 0);
    const totalLiquidoPlataforma = lancamentos.reduce((soma, l) => soma + (l.liqPlat || 0), 0);
    const totalDespesas = lancamentos.reduce(
      (soma, l) => soma + l.despesas.reduce((s, d) => s + (d.valor || 0), 0),
      0
    );
    const taxasApp = Math.max(0, faturamentoBruto - totalLiquidoPlataforma);
    const totalTaxasDespesas = taxasApp + totalDespesas;
    const lucroLiquido = totalLiquidoPlataforma - totalDespesas;
    const margemLucro = faturamentoBruto > 0 ? (lucroLiquido / faturamentoBruto) * 100 : 0;

    const porSite: Record<string, number> = {};
    lancamentos.forEach((l) => {
      if (l.site) porSite[l.site] = (porSite[l.site] || 0) + (l.bruto || 0);
    });
    const melhorSite = Object.entries(porSite).sort((a, b) => b[1] - a[1])[0]?.[0] || "—";

    return {
      faturamentoBruto,
      taxasApp,
      totalDespesas,
      totalTaxasDespesas,
      lucroLiquido,
      margemLucro,
      registros: lancamentos.length,
      melhorSite,
    };
  }, [dados]);

  async function salvarDespesaGeral() {
    if (!dImovelId) {
      Alert.alert("Selecione um imóvel.");
      return;
    }
    const valorNumerico = parseFloat(dValor.replace(",", "."));
    if (!valorNumerico || valorNumerico <= 0) {
      Alert.alert("Informe um valor válido.");
      return;
    }
    setSalvandoDespesa(true);
    try {
      await apiFetch("/api/despesas-gerais", {
        method: "POST",
        token,
        body: { imovel_id: dImovelId, categoria: dCategoria, valor: valorNumerico },
      });
      setModalDespesa(false);
      setDValor("");
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível salvar a despesa.");
    } finally {
      setSalvandoDespesa(false);
    }
  }

  function adicionarLinhaDespesa() {
    setLDespesas((atual) => [...atual, { nome: "", valor: "" }]);
  }

  function removerLinhaDespesa(index: number) {
    setLDespesas((atual) => atual.filter((_, i) => i !== index));
  }

  async function salvarNovoLancamento() {
    if (!lImovel.trim()) {
      Alert.alert("Selecione o imóvel.");
      return;
    }
    setSalvandoLancamento(true);
    try {
      await apiFetch("/api/financas", {
        method: "POST",
        token,
        body: {
          imovel: lImovel,
          site: lSite || null,
          status: lStatus || null,
          entrada: lEntrada || null,
          bruto: parseFloat(lBruto.replace(",", ".")) || 0,
          liqPlat: parseFloat(lLiqPlat.replace(",", ".")) || 0,
          despesas: lDespesas
            .filter((d) => d.nome.trim())
            .map((d) => ({ nome: d.nome.trim(), valor: parseFloat(d.valor.replace(",", ".")) || 0 })),
        },
      });
      setModalLancamento(false);
      setLSite("");
      setLStatus("");
      setLEntrada("");
      setLBruto("");
      setLLiqPlat("");
      setLDespesas([]);
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível salvar o lançamento.");
    } finally {
      setSalvandoLancamento(false);
    }
  }

  function confirmarExclusao(item: LancamentoFinanceiro) {
    Alert.alert("Excluir lançamento", `Excluir este lançamento de "${item.imovel}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir",
        style: "destructive",
        onPress: async () => {
          try {
            const path =
              item.tipo === "despesa_geral"
                ? `/api/despesas-gerais/${item.id}`
                : `/api/financas/${item.id}`;
            await apiFetch(path, { method: "DELETE", token });
            await carregar();
          } catch (e: any) {
            Alert.alert("Erro", e.message || "Não foi possível excluir.");
          }
        },
      },
    ]);
  }

  if (carregando) {
    return (
      <View style={styles.centro}>
        <ActivityIndicator size="large" color={cores.primaria} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.titulo}>Fluxo de Caixa</Text>
          <Text style={styles.subtitulo}>Rentabilidade detalhada de lançamentos</Text>
        </View>
        <TouchableOpacity style={styles.botaoNovo} onPress={() => setModalLancamento(true)}>
          <Text style={styles.botaoNovoTexto}>+ Lançamento</Text>
        </TouchableOpacity>
      </View>

      {erro ? (
        <View style={styles.alertaErro}>
          <Text style={styles.alertaErroTexto}>{erro}</Text>
        </View>
      ) : null}

      <ScrollView
        style={{ flex: 1 }}
        refreshControl={
          <RefreshControl
            refreshing={atualizando}
            onRefresh={() => {
              setAtualizando(true);
              carregar();
            }}
          />
        }
      >
        <View style={styles.kpisGrid}>
          <Kpi label="Lucro Líquido" valor={`R$ ${formatarMoeda(kpis.lucroLiquido)}`} cor="#0284c7" />
          <Kpi label="Faturamento Bruto" valor={`R$ ${formatarMoeda(kpis.faturamentoBruto)}`} cor="#16a34a" />
          <Kpi label="Total Taxas + Despesas" valor={`R$ ${formatarMoeda(kpis.totalTaxasDespesas)}`} cor="#dc2626" />
          <Kpi label="Margem de Lucro" valor={`${kpis.margemLucro.toFixed(1)}%`} cor="#f59e0b" />
          <Kpi label="Registros" valor={String(kpis.registros)} cor="#9333ea" />
          <Kpi label="Melhor Site" valor={kpis.melhorSite} cor="#0052D4" />
        </View>

        <View style={styles.filtrosBox}>
          <Text style={styles.label}>Pesquisar Imóvel</Text>
          <TextInput
            style={styles.input}
            value={busca}
            onChangeText={setBusca}
            placeholder="Buscar por nome..."
            placeholderTextColor="#9ca3af"
          />
          <View style={styles.filtroLinha}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Filtrar Imóvel</Text>
              <View style={styles.pickerWrap}>
                <Picker selectedValue={filtroImovel} onValueChange={setFiltroImovel}>
                  <Picker.Item label="Todos os imóveis" value="" />
                  {(dados?.imoveis || []).map((i) => (
                    <Picker.Item key={i.id} label={i.titulo} value={i.titulo} />
                  ))}
                </Picker>
              </View>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Site/Provedor</Text>
              <View style={styles.pickerWrap}>
                <Picker selectedValue={filtroSite} onValueChange={setFiltroSite}>
                  <Picker.Item label="Todos os sites" value="" />
                  {sitesDisponiveis.map((s) => (
                    <Picker.Item key={s} label={s} value={s} />
                  ))}
                </Picker>
              </View>
            </View>
          </View>
        </View>

        <View style={{ gap: 10 }}>
          {lancamentosFiltrados.length === 0 ? (
            <Text style={styles.vazio}>Nenhum lançamento ainda.</Text>
          ) : (
            lancamentosFiltrados.map((item, index) => (
              <TouchableOpacity
                key={`${item.tipo}-${item.id}-${index}`}
                style={styles.linha}
                onLongPress={() => item.editavel && confirmarExclusao(item)}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.linhaImovel} numberOfLines={1}>
                    {item.imovel || "—"}
                  </Text>
                  <Text style={styles.linhaSub}>
                    {TIPO_LABEL[item.tipo] || item.tipo} · {item.site || "sem canal"} ·{" "}
                    {item.entrada || item.data || "sem data"}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.linhaBruto}>R$ {formatarMoeda(item.bruto)}</Text>
                  <Text style={styles.linhaLiquido}>líq. R$ {formatarMoeda(item.liqPlat)}</Text>
                </View>
              </TouchableOpacity>
            ))
          )}
        </View>

        <TouchableOpacity style={styles.botaoDespesaGeral} onPress={() => setModalDespesa(true)}>
          <Text style={styles.botaoDespesaGeralTexto}>+ Despesa geral rápida</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Modal: Novo Lançamento (fluxo de caixa completo) */}
      <Modal visible={modalLancamento} animationType="slide" transparent>
        <View style={styles.modalFundo}>
          <View style={[styles.modalConteudo, { maxHeight: "88%" }]}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitulo}>Novo Lançamento</Text>

              <Text style={styles.label}>Imóvel *</Text>
              <View style={styles.pickerWrap}>
                <Picker selectedValue={lImovel} onValueChange={setLImovel}>
                  <Picker.Item label="Selecione o imóvel..." value="" />
                  {(dados?.imoveis || []).map((i) => (
                    <Picker.Item key={i.id} label={i.titulo} value={i.titulo} />
                  ))}
                </Picker>
              </View>

              <Text style={styles.label}>Canal de Origem</Text>
              <TextInput
                style={styles.input}
                value={lSite}
                onChangeText={setLSite}
                placeholder="Ex: Airbnb, Booking, Direto..."
                placeholderTextColor="#9ca3af"
              />

              <Text style={styles.label}>Status</Text>
              <TextInput
                style={styles.input}
                value={lStatus}
                onChangeText={setLStatus}
                placeholder="Ex: Confirmada"
                placeholderTextColor="#9ca3af"
              />

              <Text style={styles.label}>Data (AAAA-MM-DD)</Text>
              <TextInput
                style={styles.input}
                value={lEntrada}
                onChangeText={setLEntrada}
                placeholder="2026-08-06"
                placeholderTextColor="#9ca3af"
              />

              <View style={styles.filtroLinha}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Valor Bruto</Text>
                  <TextInput
                    style={styles.input}
                    value={lBruto}
                    onChangeText={setLBruto}
                    placeholder="0,00"
                    placeholderTextColor="#9ca3af"
                    keyboardType="decimal-pad"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Valor Líquido</Text>
                  <TextInput
                    style={styles.input}
                    value={lLiqPlat}
                    onChangeText={setLLiqPlat}
                    placeholder="0,00"
                    placeholderTextColor="#9ca3af"
                    keyboardType="decimal-pad"
                  />
                </View>
              </View>

              <Text style={styles.label}>Despesas</Text>
              {lDespesas.map((d, i) => (
                <View key={i} style={[styles.filtroLinha, { marginBottom: 8 }]}>
                  <TextInput
                    style={[styles.input, { flex: 2, marginBottom: 0 }]}
                    value={d.nome}
                    onChangeText={(v) =>
                      setLDespesas((atual) => atual.map((x, idx) => (idx === i ? { ...x, nome: v } : x)))
                    }
                    placeholder="Ex: Conta de água"
                    placeholderTextColor="#9ca3af"
                  />
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    value={d.valor}
                    onChangeText={(v) =>
                      setLDespesas((atual) => atual.map((x, idx) => (idx === i ? { ...x, valor: v } : x)))
                    }
                    placeholder="0,00"
                    placeholderTextColor="#9ca3af"
                    keyboardType="decimal-pad"
                  />
                  <TouchableOpacity onPress={() => removerLinhaDespesa(i)} style={styles.botaoRemoverLinha}>
                    <Text style={{ color: cores.perigo, fontWeight: "800" }}>×</Text>
                  </TouchableOpacity>
                </View>
              ))}
              <TouchableOpacity onPress={adicionarLinhaDespesa} style={{ marginBottom: 14 }}>
                <Text style={{ color: cores.primaria, fontWeight: "700", fontSize: 13 }}>+ Adicionar despesa</Text>
              </TouchableOpacity>

              <View style={styles.modalBotoes}>
                <TouchableOpacity style={styles.modalBotaoCancelar} onPress={() => setModalLancamento(false)}>
                  <Text style={styles.modalBotaoCancelarTexto}>Cancelar</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.modalBotaoSalvar}
                  onPress={salvarNovoLancamento}
                  disabled={salvandoLancamento}
                >
                  {salvandoLancamento ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.modalBotaoSalvarTexto}>SALVAR LANÇAMENTO</Text>
                  )}
                </TouchableOpacity>
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Modal: Despesa Geral rápida */}
      <Modal visible={modalDespesa} animationType="slide" transparent>
        <View style={styles.modalFundo}>
          <View style={styles.modalConteudo}>
            <Text style={styles.modalTitulo}>Nova Despesa Geral</Text>

            <Text style={styles.label}>Imóvel</Text>
            <View style={styles.pickerWrap}>
              <Picker selectedValue={dImovelId} onValueChange={(v) => setDImovelId(v)}>
                {(dados?.imoveis || []).map((i) => (
                  <Picker.Item key={i.id} label={i.titulo} value={i.id} />
                ))}
              </Picker>
            </View>

            <Text style={styles.label}>Categoria</Text>
            <View style={styles.pickerWrap}>
              <Picker selectedValue={dCategoria} onValueChange={setDCategoria}>
                {CATEGORIAS_DESPESA.map((c) => (
                  <Picker.Item key={c} label={c} value={c} />
                ))}
              </Picker>
            </View>

            <Text style={styles.label}>Valor (R$)</Text>
            <TextInput
              style={styles.input}
              value={dValor}
              onChangeText={setDValor}
              placeholder="0,00"
              placeholderTextColor="#9ca3af"
              keyboardType="decimal-pad"
            />

            <View style={styles.modalBotoes}>
              <TouchableOpacity style={styles.modalBotaoCancelar} onPress={() => setModalDespesa(false)}>
                <Text style={styles.modalBotaoCancelarTexto}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalBotaoSalvar} onPress={salvarDespesaGeral} disabled={salvandoDespesa}>
                {salvandoDespesa ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.modalBotaoSalvarTexto}>Salvar</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: cores.fundo, padding: 20 },
  centro: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 14,
    gap: 10,
  },
  titulo: { fontSize: 22, fontWeight: "800", color: cores.textoEscuro },
  subtitulo: { fontSize: 12, color: cores.textoMuted, marginTop: 2 },
  botaoNovo: {
    backgroundColor: cores.primaria,
    borderRadius: raio.sm,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  botaoNovoTexto: { color: "#fff", fontWeight: "700", fontSize: 12.5 },
  alertaErro: {
    backgroundColor: cores.perigoClaro,
    borderRadius: raio.sm,
    padding: 12,
    marginBottom: 12,
  },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  kpisGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 16 },
  kpiCard: {
    width: "31.5%",
    backgroundColor: cores.cardFundo,
    borderRadius: raio.md,
    padding: 12,
    overflow: "hidden",
    ...sombraCard,
  },
  kpiBarra: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4 },
  kpiLabel: {
    fontSize: 9.5,
    fontWeight: "700",
    color: cores.textoMuted,
    textTransform: "uppercase",
    marginBottom: 5,
  },
  kpiValor: { fontSize: 13, fontWeight: "800", color: cores.textoEscuro },
  filtrosBox: {
    backgroundColor: cores.cardFundo,
    borderRadius: raio.md,
    padding: 14,
    marginBottom: 16,
    ...sombraCard,
  },
  filtroLinha: { flexDirection: "row", gap: 10 },
  vazio: { textAlign: "center", color: "#9ca3af", marginTop: 20 },
  linha: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: cores.cardFundo,
    borderRadius: raio.md,
    padding: 14,
  },
  linhaImovel: { fontWeight: "700", color: cores.textoEscuro, fontSize: 14 },
  linhaSub: { fontSize: 11.5, color: "#9ca3af", marginTop: 2 },
  linhaBruto: { fontWeight: "800", color: cores.textoEscuro, fontSize: 14 },
  linhaLiquido: { fontSize: 11.5, color: cores.sucesso, marginTop: 2 },
  botaoDespesaGeral: { alignItems: "center", paddingVertical: 16, marginBottom: 24 },
  botaoDespesaGeralTexto: { color: cores.primaria, fontWeight: "700", fontSize: 13 },
  modalFundo: { flex: 1, backgroundColor: "rgba(15,23,42,0.55)", justifyContent: "center", padding: 24 },
  modalConteudo: { backgroundColor: cores.cardFundo, borderRadius: raio.lg + 4, padding: 22 },
  modalTitulo: { fontSize: 18, fontWeight: "800", marginBottom: 16, color: cores.textoEscuro },
  label: { fontWeight: "600", marginBottom: 6, fontSize: 13, color: cores.textoEscuro },
  pickerWrap: {
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: raio.sm,
    marginBottom: 14,
    overflow: "hidden",
  },
  input: {
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: raio.sm,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    marginBottom: 14,
    backgroundColor: cores.primariaClara,
    color: cores.textoEscuro,
  },
  botaoRemoverLinha: { width: 36, alignItems: "center", justifyContent: "center" },
  modalBotoes: { flexDirection: "row", gap: 10, marginTop: 4 },
  modalBotaoCancelar: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: raio.sm,
    alignItems: "center",
    backgroundColor: "#f1f5f9",
  },
  modalBotaoCancelarTexto: { color: cores.textoEscuro, fontWeight: "700" },
  modalBotaoSalvar: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: raio.sm,
    alignItems: "center",
    backgroundColor: cores.primaria,
  },
  modalBotaoSalvarTexto: { color: "#fff", fontWeight: "700" },
});
