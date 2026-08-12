import React, { useCallback, useEffect, useState } from "react";
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
} from "react-native";
import { Picker } from "@react-native-picker/picker";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { HubResponse, HubImovelScore, HubTarefaItem } from "../types";
import { cores, raio, sombraCard } from "../theme";

// Espelha app/templates/hub_anfitriao.html ("Hub Inteligente" / "Central
// Operacional"): "Prioridades do Dia" (próximo check-in + score por
// imóvel) e "Cuidados do Imóvel" (tarefas de manutenção/limpeza/pilha).
// Checklists, Rotinas e Precificação ainda não têm API mobile (ver
// app/routes/api.py) — ficam pra uma próxima versão do app.
const CORES_NIVEL: Record<string, string> = {
  excelente: cores.sucesso,
  atencao: cores.aviso,
  critico: cores.perigo,
};

function Kpi({ label, valor, cor }: { label: string; valor: string; cor: string }) {
  return (
    <View style={styles.kpiCard}>
      <View style={[styles.kpiBarra, { backgroundColor: cor }]} />
      <Text style={styles.kpiLabel}>{label}</Text>
      <Text style={styles.kpiValor}>{valor}</Text>
    </View>
  );
}

export default function HubScreen() {
  const { token } = useAuth();
  const [dados, setDados] = useState<HubResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [modalAberto, setModalAberto] = useState(false);
  const [imovelId, setImovelId] = useState<number | null>(null);
  const [tituloManutencao, setTituloManutencao] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await apiFetch<HubResponse>("/api/hub-tarefas", { token });
      setDados(resposta);
      if (!imovelId && resposta.imoveis.length > 0) {
        setImovelId(resposta.imoveis[0].id);
      }
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar o Hub.");
    } finally {
      setCarregando(false);
      setAtualizando(false);
    }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    carregar();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function registrarManutencao() {
    if (!imovelId || !tituloManutencao.trim()) {
      Alert.alert("Selecione o imóvel e descreva a manutenção.");
      return;
    }
    setSalvando(true);
    try {
      await apiFetch("/api/hub-tarefas/manutencao", {
        method: "POST",
        token,
        body: { imovel_id: imovelId, titulo: tituloManutencao.trim() },
      });
      setModalAberto(false);
      setTituloManutencao("");
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível registrar.");
    } finally {
      setSalvando(false);
    }
  }

  async function trocarPilha(imovel: HubImovelScore) {
    try {
      await apiFetch(`/api/hub-tarefas/troca-pilha/${imovel.id}`, { method: "POST", token });
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível registrar a troca.");
    }
  }

  async function concluirTarefa(tarefa: HubTarefaItem) {
    try {
      await apiFetch(`/api/hub-tarefas/${tarefa.id}/concluir`, { method: "POST", token });
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível concluir.");
    }
  }

  function excluirTarefa(tarefa: HubTarefaItem) {
    Alert.alert("Excluir tarefa", `Excluir "${tarefa.titulo}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir",
        style: "destructive",
        onPress: async () => {
          try {
            await apiFetch(`/api/hub-tarefas/${tarefa.id}`, { method: "DELETE", token });
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
          <Text style={styles.titulo}>Hub Inteligente</Text>
          <Text style={styles.subtitulo}>Central Operacional</Text>
        </View>
        <TouchableOpacity style={styles.botaoNovo} onPress={() => setModalAberto(true)}>
          <Text style={styles.botaoNovoTexto}>+ Manutenção</Text>
        </TouchableOpacity>
      </View>

      {erro ? (
        <View style={styles.alertaErro}>
          <Text style={styles.alertaErroTexto}>{erro}</Text>
        </View>
      ) : null}

      <View style={styles.kpisGrid}>
        <Kpi label="Manutenções abertas" valor={String(dados?.manutencoes_abertas ?? 0)} cor="#ea580c" />
        <Kpi label="Limpezas pendentes" valor={String(dados?.limpezas_pendentes ?? 0)} cor={cores.sucesso} />
        <Kpi label="Pilhas vencidas" valor={String(dados?.pilhas_vencidas ?? 0)} cor={cores.aviso} />
        <Kpi label="Tarefas pendentes" valor={String(dados?.tarefas_pendentes_total ?? 0)} cor="#0284c7" />
      </View>

      <FlatList
        data={dados?.tarefas || []}
        keyExtractor={(t) => String(t.id)}
        contentContainerStyle={{ gap: 8, paddingBottom: 40 }}
        refreshControl={
          <RefreshControl
            refreshing={atualizando}
            onRefresh={() => {
              setAtualizando(true);
              carregar();
            }}
          />
        }
        ListHeaderComponent={
          <>
            <Text style={styles.secaoTitulo}>⚡ Prioridades do Dia</Text>
            {dados?.proximo_checkin ? (
              <View style={styles.checkinCard}>
                <Text style={styles.checkinTitulo}>
                  🗓️ Próximo check-in: {dados.proximo_checkin.quando}
                  {dados.proximo_checkin.hora ? ` às ${dados.proximo_checkin.hora}` : ""}
                </Text>
                <Text style={styles.checkinTexto}>
                  {dados.proximo_checkin.hospede} · {dados.proximo_checkin.imovel}
                </Text>
              </View>
            ) : (
              <Text style={styles.vazio}>Nenhum check-in agendado.</Text>
            )}

            <View style={styles.secaoComBotao}>
              <Text style={styles.secaoTitulo}>🧹 Cuidados do Imóvel</Text>
            </View>
            <Text style={styles.secaoSub}>Score por imóvel</Text>
            {(dados?.imoveis || []).map((im) => (
              <View key={im.id} style={styles.scoreCard}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.scoreTitulo}>{im.titulo}</Text>
                  {im.alertas.length > 0 ? (
                    <Text style={styles.scoreAlerta}>{im.alertas.join(" · ")}</Text>
                  ) : (
                    <Text style={styles.scoreOk}>Tudo em dia</Text>
                  )}
                </View>
                <View style={styles.scoreBadgeWrap}>
                  <View style={[styles.scoreBadge, { backgroundColor: CORES_NIVEL[im.nivel] || "#9ca3af" }]}>
                    <Text style={styles.scoreBadgeTexto}>{im.score}</Text>
                  </View>
                  {im.dias_pilha !== null && im.dias_pilha >= 20 ? (
                    <TouchableOpacity style={styles.botaoPilha} onPress={() => trocarPilha(im)}>
                      <Text style={styles.botaoPilhaTexto}>🔋 Pilha trocada</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
              </View>
            ))}

            <Text style={[styles.secaoSub, { marginTop: 14 }]}>Tarefas pendentes</Text>
          </>
        }
        ListEmptyComponent={<Text style={styles.vazio}>Nenhuma tarefa pendente 🎉</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.tarefaCard} onLongPress={() => excluirTarefa(item)}>
            <Text style={styles.tarefaIcone}>{item.tipo_icone}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.tarefaTitulo} numberOfLines={2}>
                {item.titulo}
              </Text>
              <Text style={styles.tarefaSub}>
                {item.imovel} · {item.tipo_label}
              </Text>
            </View>
            <TouchableOpacity style={styles.botaoConcluir} onPress={() => concluirTarefa(item)}>
              <Text style={styles.botaoConcluirTexto}>✓</Text>
            </TouchableOpacity>
          </TouchableOpacity>
        )}
      />

      <Modal visible={modalAberto} animationType="slide" transparent>
        <View style={styles.modalFundo}>
          <View style={styles.modalConteudo}>
            <Text style={styles.modalTitulo}>Registrar Manutenção</Text>

            <Text style={styles.label}>Imóvel</Text>
            <View style={styles.pickerWrap}>
              <Picker selectedValue={imovelId} onValueChange={(v) => setImovelId(v)}>
                {(dados?.imoveis || []).map((i) => (
                  <Picker.Item key={i.id} label={i.titulo} value={i.id} />
                ))}
              </Picker>
            </View>

            <Text style={styles.label}>O que precisa ser feito?</Text>
            <TextInput
              style={styles.input}
              value={tituloManutencao}
              onChangeText={setTituloManutencao}
              placeholder="Ex: Trocar chuveiro do banheiro"
              placeholderTextColor="#9ca3af"
            />

            <View style={styles.modalBotoes}>
              <TouchableOpacity style={styles.modalBotaoCancelar} onPress={() => setModalAberto(false)}>
                <Text style={styles.modalBotaoCancelarTexto}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalBotaoSalvar} onPress={registrarManutencao} disabled={salvando}>
                {salvando ? (
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
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14, gap: 10 },
  titulo: { fontSize: 22, fontWeight: "800", color: cores.textoEscuro },
  subtitulo: { fontSize: 12, color: cores.textoMuted, marginTop: 2 },
  botaoNovo: { backgroundColor: cores.primaria, borderRadius: raio.sm, paddingVertical: 10, paddingHorizontal: 14 },
  botaoNovoTexto: { color: "#fff", fontWeight: "700", fontSize: 12 },
  alertaErro: { backgroundColor: cores.perigoClaro, borderRadius: raio.sm, padding: 12, marginBottom: 12 },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  kpisGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 12 },
  kpiCard: { width: "47%", backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 14, overflow: "hidden", ...sombraCard },
  kpiBarra: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4 },
  kpiLabel: { fontSize: 10.5, fontWeight: "700", color: cores.textoMuted, textTransform: "uppercase", marginBottom: 6 },
  kpiValor: { fontSize: 17, fontWeight: "800", color: cores.textoEscuro },
  checkinCard: { backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 14, marginBottom: 16, borderLeftWidth: 4, borderLeftColor: cores.primaria },
  checkinTitulo: { fontWeight: "700", color: cores.textoEscuro },
  checkinTexto: { color: cores.textoMuted, marginTop: 2, fontSize: 12.5 },
  secaoTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 15, marginTop: 8, marginBottom: 10 },
  secaoComBotao: { marginTop: 4 },
  secaoSub: { fontWeight: "700", color: cores.textoMuted, fontSize: 12, marginBottom: 8, textTransform: "uppercase" },
  scoreCard: { flexDirection: "row", alignItems: "center", backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 14, marginBottom: 8 },
  scoreTitulo: { fontWeight: "700", color: cores.textoEscuro, fontSize: 14 },
  scoreAlerta: { fontSize: 11.5, color: cores.perigo, marginTop: 2 },
  scoreOk: { fontSize: 11.5, color: cores.sucesso, marginTop: 2 },
  scoreBadgeWrap: { alignItems: "flex-end", gap: 6 },
  scoreBadge: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  scoreBadgeTexto: { color: "#fff", fontWeight: "800", fontSize: 12 },
  botaoPilha: { backgroundColor: "#fef3c7", borderRadius: raio.sm, paddingVertical: 4, paddingHorizontal: 8 },
  botaoPilhaTexto: { fontSize: 10.5, fontWeight: "700", color: "#92400e" },
  vazio: { textAlign: "center", color: "#9ca3af", marginTop: 12, marginBottom: 12 },
  tarefaCard: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 12 },
  tarefaIcone: { fontSize: 20 },
  tarefaTitulo: { fontWeight: "700", color: cores.textoEscuro, fontSize: 13.5 },
  tarefaSub: { fontSize: 11.5, color: "#9ca3af", marginTop: 2 },
  botaoConcluir: { width: 32, height: 32, borderRadius: 16, backgroundColor: "#dcfce7", alignItems: "center", justifyContent: "center" },
  botaoConcluirTexto: { color: cores.sucesso, fontWeight: "800" },
  modalFundo: { flex: 1, backgroundColor: "rgba(15,23,42,0.55)", justifyContent: "center", padding: 24 },
  modalConteudo: { backgroundColor: cores.cardFundo, borderRadius: raio.lg + 4, padding: 22 },
  modalTitulo: { fontSize: 18, fontWeight: "800", marginBottom: 16, color: cores.textoEscuro },
  label: { fontWeight: "600", marginBottom: 6, fontSize: 13, color: cores.textoEscuro },
  pickerWrap: { borderWidth: 1, borderColor: cores.borda, borderRadius: raio.sm, marginBottom: 14, overflow: "hidden" },
  input: { borderWidth: 1, borderColor: cores.borda, borderRadius: raio.sm, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, marginBottom: 14, backgroundColor: cores.primariaClara, color: cores.textoEscuro },
  modalBotoes: { flexDirection: "row", gap: 10, marginTop: 4 },
  modalBotaoCancelar: { flex: 1, paddingVertical: 12, borderRadius: raio.sm, alignItems: "center", backgroundColor: "#f1f5f9" },
  modalBotaoCancelarTexto: { color: cores.textoEscuro, fontWeight: "700" },
  modalBotaoSalvar: { flex: 1, paddingVertical: 12, borderRadius: raio.sm, alignItems: "center", backgroundColor: cores.primaria },
  modalBotaoSalvarTexto: { color: "#fff", fontWeight: "700" },
});
