import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useAuth } from "../contexts/AuthContext";
import { cores, raio } from "../theme";

// Espelha app/templates/login.html (que estende base_auth.html): logo
// no topo, cartão branco central com o formulário de e-mail/senha.
export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function handleLogin() {
    setErro(null);
    setEnviando(true);
    try {
      await login(email.trim().toLowerCase(), senha);
    } catch (e: any) {
      setErro(e.message || "Não foi possível entrar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.logoWrap}>
        <View style={styles.iconCircle}>
          <Text style={styles.iconText}>N</Text>
        </View>
        <Text style={styles.logoText}>Nomdo</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>Entrar</Text>
        <Text style={styles.subtitle}>Acesse sua conta pra gerenciar seus imóveis.</Text>

        {erro ? (
          <View style={styles.alertaErro}>
            <Text style={styles.alertaErroTexto}>{erro}</Text>
          </View>
        ) : null}

        <View style={styles.grupo}>
          <Text style={styles.label}>E-mail</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            placeholder="voce@email.com"
            placeholderTextColor="#9ca3af"
            autoCapitalize="none"
            keyboardType="email-address"
          />
        </View>

        <View style={styles.grupo}>
          <Text style={styles.label}>Senha</Text>
          <TextInput
            style={styles.input}
            value={senha}
            onChangeText={setSenha}
            placeholder="••••••••"
            placeholderTextColor="#9ca3af"
            secureTextEntry
          />
        </View>

        <TouchableOpacity
          style={[styles.botao, (enviando || !email || !senha) && styles.botaoDesabilitado]}
          onPress={handleLogin}
          disabled={enviando || !email || !senha}
        >
          {enviando ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.botaoTexto}>Entrar</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: cores.fundo,
    padding: 24,
    justifyContent: "center",
  },
  logoWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 32,
    alignSelf: "center",
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: cores.primaria,
    alignItems: "center",
    justifyContent: "center",
  },
  iconText: { color: "#fff", fontWeight: "700", fontSize: 20 },
  logoText: { fontSize: 22, fontWeight: "700", color: cores.textoEscuro },
  card: {
    backgroundColor: cores.cardFundo,
    borderRadius: raio.lg,
    padding: 24,
    borderWidth: 1,
    borderColor: cores.borda,
  },
  title: { fontSize: 26, fontWeight: "800", color: cores.textoEscuro },
  subtitle: { color: cores.textoMuted, marginTop: 6, marginBottom: 22 },
  alertaErro: {
    backgroundColor: cores.perigoClaro,
    borderRadius: raio.sm,
    padding: 12,
    marginBottom: 16,
  },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600", textAlign: "center" },
  grupo: { marginBottom: 16 },
  label: { fontWeight: "600", marginBottom: 8, fontSize: 13, color: cores.textoEscuro },
  input: {
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: raio.sm,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    backgroundColor: cores.primariaClara,
    color: cores.textoEscuro,
  },
  botao: {
    backgroundColor: cores.primaria,
    borderRadius: raio.sm,
    paddingVertical: 15,
    alignItems: "center",
    marginTop: 8,
  },
  botaoDesabilitado: { opacity: 0.6 },
  botaoTexto: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
