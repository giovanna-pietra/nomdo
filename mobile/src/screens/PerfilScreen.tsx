import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Switch,
  Alert,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Picker } from "@react-native-picker/picker";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { Perfil } from "../types";
import { cores, raio } from "../theme";

// Espelha app/templates/usuario.html: "Editar Perfil", categoria em dois
// cartões (Anfitrião/Proprietário), notificações e "Excluir minha conta".
export default function PerfilScreen() {
  const { token, logout, user } = useAuth();
  const navigation = useNavigation<any>();
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [genero, setGenero] = useState("");
  const [categoria, setCategoria] = useState("Anfitrião");
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifyBrowser, setNotifyBrowser] = useState(true);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await apiFetch<{ perfil: Perfil }>("/api/perfil", { token });
      setPerfil(resposta.perfil);
      setNome(resposta.perfil.nome);
      setTelefone(resposta.perfil.telefone || "");
      setGenero(resposta.perfil.genero || "");
      setCategoria(resposta.perfil.categoria || "Anfitrião");
      setNotifyEmail(resposta.perfil.notify_email);
      setNotifyBrowser(resposta.perfil.notify_browser);
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar o perfil.");
    } finally {
      setCarregando(false);
    }
  }, [token]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function salvarPerfil() {
    setErro(null);
    setSucesso(null);
    setSalvando(true);
    try {
      await apiFetch("/api/perfil", {
        method: "PUT",
        token,
        body: { nome, telefone, genero, categoria },
      });
      await apiFetch("/api/perfil/configuracoes", {
        method: "PUT",
        token,
        body: { notify_email: notifyEmail, notify_browser: notifyBrowser },
      });
      setSucesso("Perfil atualizado com sucesso!");
      await carregar();
    } catch (e: any) {
      setErro(e.message || "Não foi possível salvar.");
    } finally {
      setSalvando(false);
    }
  }

  function confirmarExclusaoConta() {
    Alert.alert(
      "Excluir conta permanentemente?",
      "Esta ação é irreversível. Todos os seus dados serão apagados.",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Sim, excluir tudo",
          style: "destructive",
          onPress: async () => {
            try {
              await apiFetch("/api/perfil", { method: "DELETE", token });
              await logout();
            } catch (e: any) {
              Alert.alert("Erro", e.message || "Não foi possível excluir a conta.");
            }
          },
        },
      ]
    );
  }

  if (carregando) {
    return (
      <View style={styles.centro}>
        <ActivityIndicator size="large" color={cores.primaria} />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
      <Text style={styles.titulo}>Editar Perfil</Text>
      <Text style={styles.email}>{perfil?.email}</Text>

      {erro ? (
        <View style={styles.alertaErro}>
          <Text style={styles.alertaErroTexto}>{erro}</Text>
        </View>
      ) : null}
      {sucesso ? (
        <View style={styles.alertaSucesso}>
          <Text style={styles.alertaSucessoTexto}>{sucesso}</Text>
        </View>
      ) : null}

      {user?.is_admin ? (
        <TouchableOpacity style={styles.painelMasterBanner} onPress={() => navigation.navigate("Admin")}>
          <View style={{ flex: 1 }}>
            <Text style={styles.painelMasterTitulo}>Painel Master</Text>
            <Text style={styles.painelMasterDesc}>Área administrativa — visível só pra contas admin.</Text>
          </View>
          <Text style={styles.painelMasterSeta}>Entrar no Painel →</Text>
        </TouchableOpacity>
      ) : null}

      <Text style={styles.secaoTitulo}>Dados pessoais</Text>

      <Text style={styles.label}>Nome</Text>
      <TextInput style={styles.input} value={nome} onChangeText={setNome} placeholderTextColor="#9ca3af" />

      <Text style={styles.label}>Telefone</Text>
      <TextInput
        style={styles.input}
        value={telefone}
        onChangeText={setTelefone}
        keyboardType="phone-pad"
        placeholderTextColor="#9ca3af"
      />

      <Text style={styles.label}>Gênero</Text>
      <View style={styles.pickerWrap}>
        <Picker selectedValue={genero} onValueChange={setGenero}>
          <Picker.Item label="Selecione seu gênero" value="" />
          <Picker.Item label="Feminino" value="feminino" />
          <Picker.Item label="Masculino" value="masculino" />
          <Picker.Item label="Outro" value="outro" />
          <Picker.Item label="Prefiro não responder" value="prefiro_nao_dizer" />
        </Picker>
      </View>

      {!perfil?.e_ajudante ? (
        <>
          <Text style={styles.label}>Categoria (escolha uma):</Text>
          <View style={styles.categoriasRow}>
            <TouchableOpacity
              style={[styles.categoriaCard, categoria === "Anfitrião" && styles.categoriaCardAtiva]}
              onPress={() => setCategoria("Anfitrião")}
            >
              <Text style={[styles.categoriaNome, categoria === "Anfitrião" && styles.categoriaNomeAtiva]}>
                Anfitrião
              </Text>
              <Text style={[styles.categoriaDesc, categoria === "Anfitrião" && styles.categoriaDescAtiva]}>
                Ajuda a operar imóveis
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.categoriaCard, categoria === "Proprietário" && styles.categoriaCardAtiva]}
              onPress={() => setCategoria("Proprietário")}
            >
              <Text style={[styles.categoriaNome, categoria === "Proprietário" && styles.categoriaNomeAtiva]}>
                Proprietário
              </Text>
              <Text style={[styles.categoriaDesc, categoria === "Proprietário" && styles.categoriaDescAtiva]}>
                Libera o Dashboard Proprietário
              </Text>
            </TouchableOpacity>
          </View>
        </>
      ) : (
        <Text style={styles.dica}>
          Sua categoria é travada em "Anfitrião" — você opera como ajudante de outra conta.
        </Text>
      )}

      <Text style={styles.secaoTitulo}>Notificações</Text>

      <View style={styles.linhaSwitch}>
        <Text style={styles.linhaSwitchLabel}>Notificações no navegador</Text>
        <Switch value={notifyBrowser} onValueChange={setNotifyBrowser} trackColor={{ true: cores.primaria }} />
      </View>
      <View style={styles.linhaSwitch}>
        <Text style={styles.linhaSwitchLabel}>Notificações por e-mail</Text>
        <Switch value={notifyEmail} onValueChange={setNotifyEmail} trackColor={{ true: cores.primaria }} />
      </View>

      <TouchableOpacity style={styles.botaoSalvar} onPress={salvarPerfil} disabled={salvando}>
        {salvando ? <ActivityIndicator color="#fff" /> : <Text style={styles.botaoSalvarTexto}>Salvar Alterações</Text>}
      </TouchableOpacity>

      <TouchableOpacity style={styles.botaoSair} onPress={logout}>
        <Text style={styles.botaoSairTexto}>Sair</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.botaoExcluir} onPress={confirmarExclusaoConta}>
        <Text style={styles.botaoExcluirTexto}>Excluir minha conta</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: cores.fundo },
  centro: { flex: 1, alignItems: "center", justifyContent: "center" },
  titulo: { fontSize: 24, fontWeight: "800", color: cores.textoEscuro },
  email: { color: cores.textoMuted, marginTop: 4, marginBottom: 20 },
  alertaErro: { backgroundColor: cores.perigoClaro, borderRadius: raio.sm, padding: 12, marginBottom: 14 },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  alertaSucesso: { backgroundColor: "rgba(22,163,74,0.12)", borderRadius: raio.sm, padding: 12, marginBottom: 14 },
  alertaSucessoTexto: { color: "#166534", fontWeight: "600" },
  painelMasterBanner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#7f1d1d",
    borderRadius: raio.md,
    padding: 16,
    marginBottom: 20,
    gap: 10,
  },
  painelMasterTitulo: { color: "#fff", fontWeight: "800", fontSize: 14 },
  painelMasterDesc: { color: "#f6cdcd", fontSize: 11, marginTop: 2 },
  painelMasterSeta: { color: "#fff", fontWeight: "700", fontSize: 12 },
  secaoTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 14, marginTop: 12, marginBottom: 12 },
  label: { fontWeight: "600", marginBottom: 6, fontSize: 13, color: cores.textoEscuro },
  input: {
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: raio.sm,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    marginBottom: 14,
    backgroundColor: cores.cardFundo,
    color: cores.textoEscuro,
  },
  pickerWrap: { borderWidth: 1, borderColor: cores.borda, borderRadius: raio.sm, marginBottom: 14, overflow: "hidden", backgroundColor: cores.cardFundo },
  categoriasRow: { flexDirection: "row", gap: 10, marginBottom: 14 },
  categoriaCard: {
    flex: 1,
    borderWidth: 2,
    borderColor: cores.borda,
    borderRadius: raio.md,
    padding: 14,
    backgroundColor: cores.cardFundo,
  },
  categoriaCardAtiva: { borderColor: cores.primaria, backgroundColor: cores.primariaClara },
  categoriaNome: { fontWeight: "800", color: cores.textoEscuro, fontSize: 14 },
  categoriaNomeAtiva: { color: cores.primaria },
  categoriaDesc: { fontSize: 11, color: cores.textoMuted, marginTop: 4 },
  categoriaDescAtiva: { color: cores.primaria },
  dica: { color: "#9ca3af", fontSize: 12, marginBottom: 14 },
  linhaSwitch: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: cores.cardFundo,
    borderRadius: raio.sm,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 10,
  },
  linhaSwitchLabel: { fontSize: 13.5, color: cores.textoEscuro },
  botaoSalvar: { backgroundColor: cores.primaria, borderRadius: raio.sm, paddingVertical: 14, alignItems: "center", marginTop: 12 },
  botaoSalvarTexto: { color: "#fff", fontWeight: "700" },
  botaoSair: { alignItems: "center", paddingVertical: 14, marginTop: 16 },
  botaoSairTexto: { color: cores.textoEscuro, fontWeight: "700" },
  botaoExcluir: { alignItems: "center", paddingVertical: 10 },
  botaoExcluirTexto: { color: cores.perigo, fontWeight: "600", fontSize: 12.5 },
});
