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
  Image,
  ScrollView,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { Imovel, Grupo } from "../types";
import { cores, raio, sombraCard } from "../theme";

// Espelha app/templates/imoveis.html: grade de cards por imóvel, filtro
// por grupo/busca e um painel de detalhes (Localização/Acesso/Contato).
const CORES_CARD: [string, string] = ["#4364F7", "#6FB1FC"];

export default function ImoveisScreen() {
  const { token } = useAuth();
  const [imoveis, setImoveis] = useState<Imovel[]>([]);
  const [grupos, setGrupos] = useState<Grupo[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [grupoFiltro, setGrupoFiltro] = useState<number | null>(null);
  const [busca, setBusca] = useState("");
  const [modalAberto, setModalAberto] = useState(false);
  const [novoTitulo, setNovoTitulo] = useState("");
  const [novoEndereco, setNovoEndereco] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [detalheImovel, setDetalheImovel] = useState<Imovel | null>(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const [respImoveis, respGrupos] = await Promise.all([
        apiFetch<{ imoveis: Imovel[] }>("/api/imoveis", { token }),
        apiFetch<{ grupos: Grupo[] }>("/api/grupos", { token }),
      ]);
      setImoveis(respImoveis.imoveis);
      setGrupos(respGrupos.grupos);
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar os imóveis.");
    } finally {
      setCarregando(false);
      setAtualizando(false);
    }
  }, [token]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function criarImovel() {
    if (!novoTitulo.trim() || !novoEndereco.trim()) {
      Alert.alert("Preencha título e endereço.");
      return;
    }
    setSalvando(true);
    try {
      await apiFetch("/api/imoveis", {
        method: "POST",
        token,
        body: { titulo: novoTitulo.trim(), endereco: novoEndereco.trim() },
      });
      setModalAberto(false);
      setNovoTitulo("");
      setNovoEndereco("");
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível criar o imóvel.");
    } finally {
      setSalvando(false);
    }
  }

  function confirmarExclusao(imovel: Imovel) {
    Alert.alert(
      "Excluir imóvel",
      `Tem certeza que quer excluir "${imovel.titulo}"?`,
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Excluir",
          style: "destructive",
          onPress: async () => {
            try {
              await apiFetch(`/api/imoveis/${imovel.id}`, { method: "DELETE", token });
              setDetalheImovel(null);
              await carregar();
            } catch (e: any) {
              Alert.alert("Erro", e.message || "Não foi possível excluir.");
            }
          },
        },
      ]
    );
  }

  const imoveisFiltrados = useMemo(() => {
    let lista = grupoFiltro ? imoveis.filter((i) => i.grupo_id === grupoFiltro) : imoveis;
    if (busca.trim()) {
      const termo = busca.trim().toLowerCase();
      lista = lista.filter(
        (i) =>
          i.titulo.toLowerCase().includes(termo) || i.endereco.toLowerCase().includes(termo)
      );
    }
    return lista;
  }, [imoveis, grupoFiltro, busca]);

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
        <Text style={styles.titulo}>Imóveis</Text>
        <TouchableOpacity style={styles.botaoNovo} onPress={() => setModalAberto(true)}>
          <Text style={styles.botaoNovoTexto}>+ Novo Imóvel</Text>
        </TouchableOpacity>
      </View>

      <TextInput
        style={styles.busca}
        value={busca}
        onChangeText={setBusca}
        placeholder="Pesquisar imóvel..."
        placeholderTextColor="#9ca3af"
      />

      {erro ? (
        <View style={styles.alertaErro}>
          <Text style={styles.alertaErroTexto}>{erro}</Text>
        </View>
      ) : null}

      {grupos.length > 0 ? (
        <FlatList
          horizontal
          data={grupos}
          keyExtractor={(g) => String(g.id)}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, paddingBottom: 12 }}
          renderItem={({ item }) => {
            const ativo = grupoFiltro === item.id;
            return (
              <TouchableOpacity
                style={[styles.grupoPill, ativo && styles.grupoPillAtivo]}
                onPress={() => setGrupoFiltro(ativo ? null : item.id)}
              >
                <Text style={[styles.grupoPillTexto, ativo && styles.grupoPillTextoAtivo]}>
                  {item.nome} ({item.imoveis_count})
                </Text>
              </TouchableOpacity>
            );
          }}
        />
      ) : null}

      <FlatList
        data={imoveisFiltrados}
        keyExtractor={(i) => String(i.id)}
        numColumns={2}
        columnWrapperStyle={{ gap: 12 }}
        contentContainerStyle={{ gap: 12, paddingBottom: 40 }}
        refreshControl={
          <RefreshControl
            refreshing={atualizando}
            onRefresh={() => {
              setAtualizando(true);
              carregar();
            }}
          />
        }
        ListEmptyComponent={<Text style={styles.vazio}>Nenhum imóvel cadastrado ainda.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.card}
            onPress={() => setDetalheImovel(item)}
            onLongPress={() => confirmarExclusao(item)}
          >
            {item.foto_principal ? (
              <Image source={{ uri: item.foto_principal }} style={styles.cardImagem} />
            ) : (
              <LinearGradient colors={CORES_CARD} style={styles.cardImagem}>
                <Text style={styles.cardIcone}>🏠</Text>
              </LinearGradient>
            )}
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitulo} numberOfLines={1}>
                {item.titulo}
              </Text>
              <Text style={styles.cardEndereco} numberOfLines={1}>
                {item.endereco}
              </Text>
            </View>
          </TouchableOpacity>
        )}
      />

      {/* Modal: Novo Imóvel */}
      <Modal visible={modalAberto} animationType="slide" transparent>
        <View style={styles.modalFundo}>
          <View style={styles.modalConteudo}>
            <Text style={styles.modalTitulo}>Novo Imóvel</Text>

            <Text style={styles.label}>Título</Text>
            <TextInput
              style={styles.input}
              value={novoTitulo}
              onChangeText={setNovoTitulo}
              placeholder="Ex: Apto Vista Mar — Floripa"
              placeholderTextColor="#9ca3af"
            />

            <Text style={styles.label}>Endereço</Text>
            <TextInput
              style={styles.input}
              value={novoEndereco}
              onChangeText={setNovoEndereco}
              placeholder="Rua, número, bairro, cidade"
              placeholderTextColor="#9ca3af"
            />

            <View style={styles.modalBotoes}>
              <TouchableOpacity style={styles.modalBotaoCancelar} onPress={() => setModalAberto(false)}>
                <Text style={styles.modalBotaoCancelarTexto}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalBotaoSalvar}
                onPress={criarImovel}
                disabled={salvando}
              >
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

      {/* Modal: Detalhes do imóvel (Localização / Acesso / Contato) */}
      <Modal visible={!!detalheImovel} animationType="slide" transparent onRequestClose={() => setDetalheImovel(null)}>
        <View style={styles.modalFundo}>
          <View style={[styles.modalConteudo, { maxHeight: "85%" }]}>
            {detalheImovel ? (
              <ScrollView showsVerticalScrollIndicator={false}>
                <Text style={styles.modalTitulo}>{detalheImovel.titulo}</Text>
                <Text style={styles.detalheEndereco}>{detalheImovel.endereco}</Text>

                <Text style={styles.secaoTitulo}>📍 Localização</Text>
                <Text style={styles.detalheLinha}>
                  {detalheImovel.cidade || "—"}{detalheImovel.estado ? `, ${detalheImovel.estado}` : ""}
                </Text>
                {detalheImovel.ponto_referencia ? (
                  <Text style={styles.detalheLinha}>Ref: {detalheImovel.ponto_referencia}</Text>
                ) : null}

                <Text style={styles.secaoTitulo}>📶 Acesso</Text>
                <Text style={styles.detalheLinha}>Wi-Fi: {detalheImovel.wifi_rede || "—"}</Text>
                <Text style={styles.detalheLinha}>Senha Wi-Fi: {detalheImovel.wifi_senha || "—"}</Text>
                <Text style={styles.detalheLinha}>Fechadura: {detalheImovel.senha_fechadura || "—"}</Text>

                <Text style={styles.secaoTitulo}>📞 Contato do Anfitrião</Text>
                <Text style={styles.detalheLinha}>{detalheImovel.contato_telefone || "—"}</Text>
                <Text style={styles.detalheLinha}>{detalheImovel.contato_email || "—"}</Text>

                <Text style={styles.secaoTitulo}>🏠 Capacidade</Text>
                <Text style={styles.detalheLinha}>
                  {detalheImovel.capacidade_max ?? "—"} hóspedes · {detalheImovel.qtd_quartos ?? "—"} quartos ·{" "}
                  {detalheImovel.qtd_banheiros ?? "—"} banheiros · {detalheImovel.qtd_camas ?? "—"} camas
                </Text>

                <View style={styles.modalBotoes}>
                  <TouchableOpacity style={styles.modalBotaoCancelar} onPress={() => setDetalheImovel(null)}>
                    <Text style={styles.modalBotaoCancelarTexto}>Fechar</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.modalBotaoSalvar, { backgroundColor: cores.perigo }]}
                    onPress={() => confirmarExclusao(detalheImovel)}
                  >
                    <Text style={styles.modalBotaoSalvarTexto}>Excluir</Text>
                  </TouchableOpacity>
                </View>
              </ScrollView>
            ) : null}
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
    alignItems: "center",
    marginBottom: 12,
  },
  titulo: { fontSize: 24, fontWeight: "800", color: cores.textoEscuro },
  botaoNovo: {
    backgroundColor: cores.primaria,
    borderRadius: raio.sm,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  botaoNovoTexto: { color: "#fff", fontWeight: "700", fontSize: 13 },
  busca: {
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: raio.sm,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    marginBottom: 12,
    backgroundColor: cores.cardFundo,
    color: cores.textoEscuro,
  },
  alertaErro: {
    backgroundColor: cores.perigoClaro,
    borderRadius: raio.sm,
    padding: 12,
    marginBottom: 12,
  },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  grupoPill: {
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: raio.pill,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: cores.cardFundo,
  },
  grupoPillAtivo: { backgroundColor: cores.primaria, borderColor: cores.primaria },
  grupoPillTexto: { fontSize: 12, fontWeight: "700", color: cores.textoEscuro },
  grupoPillTextoAtivo: { color: "#fff" },
  vazio: { textAlign: "center", color: "#9ca3af", marginTop: 40 },
  card: {
    flex: 1,
    backgroundColor: cores.cardFundo,
    borderRadius: raio.lg,
    overflow: "hidden",
    ...sombraCard,
  },
  cardImagem: { height: 110, alignItems: "center", justifyContent: "center" },
  cardIcone: { fontSize: 32 },
  cardInfo: { padding: 12 },
  cardTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 14 },
  cardEndereco: { fontSize: 12, color: cores.textoMuted, marginTop: 2 },
  modalFundo: {
    flex: 1,
    backgroundColor: "rgba(15,23,42,0.55)",
    justifyContent: "center",
    padding: 24,
  },
  modalConteudo: { backgroundColor: cores.cardFundo, borderRadius: raio.lg + 4, padding: 22 },
  modalTitulo: { fontSize: 18, fontWeight: "800", marginBottom: 4, color: cores.textoEscuro },
  detalheEndereco: { color: cores.textoMuted, marginBottom: 14, fontSize: 12.5 },
  secaoTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 13, marginTop: 14, marginBottom: 6 },
  detalheLinha: { color: cores.textoMuted, fontSize: 13, marginBottom: 2 },
  label: { fontWeight: "600", marginBottom: 6, fontSize: 13, color: cores.textoEscuro },
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
  modalBotoes: { flexDirection: "row", gap: 10, marginTop: 16 },
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
