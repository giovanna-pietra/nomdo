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
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { EquipeResponse, AnfitriaoEquipe, ConviteEquipe } from "../types";
import { cores, raio } from "../theme";

// Espelha app/templates/equipe.html: lista "Sua equipe" + "Convites
// pendentes", com o mesmo texto usado no site.
export default function EquipeScreen() {
  const { token } = useAuth();
  const [dados, setDados] = useState<EquipeResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [bloqueado, setBloqueado] = useState(false);

  const [modalAberto, setModalAberto] = useState(false);
  const [email, setEmail] = useState("");
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await apiFetch<EquipeResponse>("/api/equipe", { token });
      setDados(resposta);
      setBloqueado(false);
    } catch (e: any) {
      if (e.status === 403) {
        setBloqueado(true);
      } else {
        setErro(e.message || "Não foi possível carregar a equipe.");
      }
    } finally {
      setCarregando(false);
      setAtualizando(false);
    }
  }, [token]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function convidar() {
    if (!email.trim()) {
      Alert.alert("Informe um e-mail.");
      return;
    }
    setEnviando(true);
    try {
      await apiFetch("/api/equipe/convidar", {
        method: "POST",
        token,
        body: { email: email.trim().toLowerCase() },
      });
      setModalAberto(false);
      setEmail("");
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível enviar o convite.");
    } finally {
      setEnviando(false);
    }
  }

  function cancelarConvite(convite: ConviteEquipe) {
    Alert.alert("Cancelar convite", `Cancelar o convite para ${convite.email}?`, [
      { text: "Voltar", style: "cancel" },
      {
        text: "Cancelar",
        style: "destructive",
        onPress: async () => {
          try {
            await apiFetch(`/api/equipe/convites/${convite.id}`, { method: "DELETE", token });
            await carregar();
          } catch (e: any) {
            Alert.alert("Erro", e.message || "Não foi possível cancelar.");
          }
        },
      },
    ]);
  }

  function removerAnfitriao(anfitriao: AnfitriaoEquipe) {
    Alert.alert("Remover da equipe", `Remover ${anfitriao.nome} da sua equipe?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Remover",
        style: "destructive",
        onPress: async () => {
          try {
            await apiFetch(`/api/equipe/anfitrioes/${anfitriao.id}`, { method: "DELETE", token });
            await carregar();
          } catch (e: any) {
            Alert.alert("Erro", e.message || "Não foi possível remover.");
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

  if (bloqueado) {
    return (
      <View style={styles.centro}>
        <Text style={styles.bloqueadoTexto}>Só a conta Proprietária pode gerenciar a equipe.</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.titulo}>Equipe</Text>
        <TouchableOpacity style={styles.botaoNovo} onPress={() => setModalAberto(true)}>
          <Text style={styles.botaoNovoTexto}>+ Convidar</Text>
        </TouchableOpacity>
      </View>

      {erro ? (
        <View style={styles.alertaErro}>
          <Text style={styles.alertaErroTexto}>{erro}</Text>
        </View>
      ) : null}

      <FlatList
        data={dados?.anfitrioes || []}
        keyExtractor={(a) => `a-${a.id}`}
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
          <Text style={styles.secaoTitulo}>👥 Sua equipe</Text>
        }
        ListEmptyComponent={<Text style={styles.vazio}>Você ainda não tem ninguém na equipe.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.linha} onLongPress={() => removerAnfitriao(item)}>
            <View style={styles.avatar}>
              <Text style={styles.avatarTexto}>{item.nome.charAt(0).toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.linhaNome}>{item.nome}</Text>
              <Text style={styles.linhaEmail}>{item.email}</Text>
            </View>
          </TouchableOpacity>
        )}
        ListFooterComponent={
          <>
            <Text style={[styles.secaoTitulo, { marginTop: 24 }]}>⏳ Convites pendentes</Text>
            <Text style={styles.secaoDesc}>Ainda não foram aceitos.</Text>
            {(dados?.convites_pendentes || []).map((c) => (
              <TouchableOpacity key={c.id} style={styles.linha} onLongPress={() => cancelarConvite(c)}>
                <View style={[styles.avatar, { backgroundColor: "#fef3c7" }]}>
                  <Text style={[styles.avatarTexto, { color: "#b8860b" }]}>✉️</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.linhaNome}>{c.email}</Text>
                  <Text style={styles.linhaEmail}>
                    Convidado em {c.criado_em}
                    {c.expirado ? " · expirado" : ""}
                  </Text>
                </View>
                <View style={styles.badgePendente}>
                  <Text style={styles.badgePendenteTexto}>Pendente</Text>
                </View>
              </TouchableOpacity>
            ))}
            {(dados?.convites_pendentes || []).length === 0 ? (
              <Text style={styles.vazio}>Nenhum convite pendente.</Text>
            ) : null}
            <Text style={styles.dica}>Toque e mantenha pressionado pra remover/cancelar.</Text>
          </>
        }
      />

      <Modal visible={modalAberto} animationType="slide" transparent>
        <View style={styles.modalFundo}>
          <View style={styles.modalConteudo}>
            <Text style={styles.modalTitulo}>Convidar Anfitrião</Text>

            <Text style={styles.label}>E-mail</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="pessoa@email.com"
              placeholderTextColor="#9ca3af"
              autoCapitalize="none"
              keyboardType="email-address"
            />

            <View style={styles.modalBotoes}>
              <TouchableOpacity style={styles.modalBotaoCancelar} onPress={() => setModalAberto(false)}>
                <Text style={styles.modalBotaoCancelarTexto}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalBotaoSalvar} onPress={convidar} disabled={enviando}>
                {enviando ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.modalBotaoSalvarTexto}>Enviar convite</Text>
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
  centro: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  bloqueadoTexto: { textAlign: "center", color: cores.textoMuted, fontSize: 14 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  titulo: { fontSize: 24, fontWeight: "800", color: cores.textoEscuro },
  botaoNovo: { backgroundColor: cores.primaria, borderRadius: raio.sm, paddingVertical: 10, paddingHorizontal: 14 },
  botaoNovoTexto: { color: "#fff", fontWeight: "700", fontSize: 13 },
  alertaErro: { backgroundColor: cores.perigoClaro, borderRadius: raio.sm, padding: 12, marginBottom: 12 },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  secaoTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 15, marginBottom: 4 },
  secaoDesc: { color: cores.textoMuted, fontSize: 12, marginBottom: 12 },
  vazio: { color: "#9ca3af", marginBottom: 8 },
  dica: { color: "#9ca3af", fontSize: 11, marginTop: 12, textAlign: "center" },
  linha: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 12 },
  avatar: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#e0e7ff", alignItems: "center", justifyContent: "center" },
  avatarTexto: { fontWeight: "800", color: cores.primaria },
  linhaNome: { fontWeight: "700", color: cores.textoEscuro, fontSize: 14 },
  linhaEmail: { fontSize: 12, color: cores.textoMuted, marginTop: 2 },
  badgePendente: { backgroundColor: "#fef3c7", borderRadius: raio.sm, paddingVertical: 4, paddingHorizontal: 8 },
  badgePendenteTexto: { color: "#92400e", fontSize: 10.5, fontWeight: "700" },
  modalFundo: { flex: 1, backgroundColor: "rgba(15,23,42,0.55)", justifyContent: "center", padding: 24 },
  modalConteudo: { backgroundColor: cores.cardFundo, borderRadius: raio.lg + 4, padding: 22 },
  modalTitulo: { fontSize: 18, fontWeight: "800", marginBottom: 16, color: cores.textoEscuro },
  label: { fontWeight: "600", marginBottom: 6, fontSize: 13, color: cores.textoEscuro },
  input: { borderWidth: 1, borderColor: cores.borda, borderRadius: raio.sm, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, marginBottom: 14, backgroundColor: cores.primariaClara, color: cores.textoEscuro },
  modalBotoes: { flexDirection: "row", gap: 10, marginTop: 4 },
  modalBotaoCancelar: { flex: 1, paddingVertical: 12, borderRadius: raio.sm, alignItems: "center", backgroundColor: "#f1f5f9" },
  modalBotaoCancelarTexto: { color: cores.textoEscuro, fontWeight: "700" },
  modalBotaoSalvar: { flex: 1, paddingVertical: 12, borderRadius: raio.sm, alignItems: "center", backgroundColor: cores.primaria },
  modalBotaoSalvarTexto: { color: "#fff", fontWeight: "700" },
});
