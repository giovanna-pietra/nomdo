import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  TextInput,
  Alert,
} from "react-native";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import {
  AdminDashboardResponse,
  AdminUsuario,
  AdminImovel,
  AdminFinanceiroResponse,
} from "../types";
import { cores, raio, sombraCard } from "../theme";

// Espelha app/templates/admin/*.html: "Central de Auditoria Master" com
// os mesmos rótulos de KPI do site (Rendimento Total, Total Imóveis,
// Total Estadias, Usuários Totais, Ativos (Último mês), Contas Inativas).
type Secao = "geral" | "usuarios" | "imoveis" | "financeiro";

function formatarMoeda(valor: number): string {
  return (valor || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Kpi({ label, valor, cor }: { label: string; valor: string; cor: string }) {
  return (
    <View style={styles.kpiCard}>
      <View style={[styles.kpiBarra, { backgroundColor: cor }]} />
      <Text style={styles.kpiLabel}>{label}</Text>
      <Text style={styles.kpiValor}>{valor}</Text>
    </View>
  );
}

function SecaoGeral({ token }: { token: string | null }) {
  const [dados, setDados] = useState<AdminDashboardResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const resposta = await apiFetch<AdminDashboardResponse>("/api/painel-master/dashboard", { token });
        setDados(resposta);
      } catch (e: any) {
        setErro(e.message || "Não foi possível carregar.");
      } finally {
        setCarregando(false);
      }
    })();
  }, [token]);

  if (carregando) return <ActivityIndicator style={{ marginTop: 30 }} color={cores.primaria} />;
  if (erro) return <Text style={styles.erroTexto}>{erro}</Text>;
  if (!dados) return null;

  const contasInativas = (dados.stats.total_usuarios || 0) - (dados.stats.usuarios_ativos || 0);

  return (
    <View>
      <View style={styles.heroAdmin}>
        <Text style={styles.heroTitulo}>🔓 Central de Auditoria Master</Text>
        <Text style={styles.heroDesc}>
          Monitore a receita transacionada pelo site e o engajamento das contas.
        </Text>
      </View>

      <View style={styles.kpisGrid}>
        <Kpi label="Rendimento Total" valor={`R$ ${dados.stats.faturamento}`} cor={cores.sucesso} />
        <Kpi label="Total Imóveis" valor={String(dados.stats.total_imoveis)} cor="#ea580c" />
        <Kpi label="Total Estadias" valor={String(dados.stats.total_estadias)} cor="#9333ea" />
        <Kpi label="Usuários Totais" valor={String(dados.stats.total_usuarios)} cor="#9333ea" />
        <Kpi label="Ativos (Último mês)" valor={String(dados.stats.novos_30d)} cor="#0284c7" />
        <Kpi label="Contas Inativas" valor={String(contasInativas)} cor={cores.perigo} />
      </View>

      <Text style={styles.secaoTitulo}>Usuários recentes</Text>
      {dados.usuarios_recentes.map((u) => (
        <View key={u.id} style={styles.linha}>
          <View style={{ flex: 1 }}>
            <Text style={styles.linhaNome}>{u.nome}</Text>
            <Text style={styles.linhaSub}>{u.email}</Text>
          </View>
          <Text style={styles.linhaData}>{u.criado_em}</Text>
        </View>
      ))}
    </View>
  );
}

function SecaoUsuarios({ token }: { token: string | null }) {
  const [usuarios, setUsuarios] = useState<AdminUsuario[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const resposta = await apiFetch<{ usuarios: AdminUsuario[] }>(
        `/api/painel-master/usuarios${busca ? `?q=${encodeURIComponent(busca)}` : ""}`,
        { token }
      );
      setUsuarios(resposta.usuarios);
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar.");
    } finally {
      setCarregando(false);
    }
  }, [token, busca]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function toggleAtivo(u: AdminUsuario) {
    try {
      await apiFetch(`/api/painel-master/usuarios/${u.id}/toggle-ativo`, { method: "POST", token });
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível atualizar.");
    }
  }

  async function toggleAdmin(u: AdminUsuario) {
    try {
      await apiFetch(`/api/painel-master/usuarios/${u.id}/toggle-admin`, { method: "POST", token });
      await carregar();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Não foi possível atualizar.");
    }
  }

  function excluir(u: AdminUsuario) {
    Alert.alert("Excluir usuário", `Excluir "${u.nome}" permanentemente?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir",
        style: "destructive",
        onPress: async () => {
          try {
            await apiFetch(`/api/painel-master/usuarios/${u.id}`, { method: "DELETE", token });
            await carregar();
          } catch (e: any) {
            Alert.alert("Erro", e.message || "Não foi possível excluir.");
          }
        },
      },
    ]);
  }

  return (
    <View>
      <TextInput
        style={styles.busca}
        placeholder="Buscar por nome ou e-mail..."
        placeholderTextColor="#9ca3af"
        value={busca}
        onChangeText={setBusca}
      />
      {carregando ? (
        <ActivityIndicator style={{ marginTop: 30 }} color={cores.primaria} />
      ) : erro ? (
        <Text style={styles.erroTexto}>{erro}</Text>
      ) : (
        usuarios.map((u) => (
          <TouchableOpacity key={u.id} style={styles.linha} onLongPress={() => excluir(u)}>
            <View style={{ flex: 1 }}>
              <Text style={styles.linhaNome}>{u.nome}</Text>
              <Text style={styles.linhaSub}>{u.email}</Text>
            </View>
            <View style={styles.badges}>
              <TouchableOpacity
                style={[styles.badge, u.is_active ? styles.badgeVerde : styles.badgeCinza]}
                onPress={() => toggleAtivo(u)}
              >
                <Text style={styles.badgeTexto}>{u.is_active ? "Ativo" : "Inativo"}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.badge, u.is_admin ? styles.badgeRoxo : styles.badgeCinza]}
                onPress={() => toggleAdmin(u)}
              >
                <Text style={styles.badgeTexto}>{u.is_admin ? "Admin" : "Usuário"}</Text>
              </TouchableOpacity>
            </View>
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}

function SecaoImoveis({ token }: { token: string | null }) {
  const [imoveis, setImoveis] = useState<AdminImovel[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const resposta = await apiFetch<{ imoveis: AdminImovel[] }>("/api/painel-master/imoveis", { token });
      setImoveis(resposta.imoveis);
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar.");
    } finally {
      setCarregando(false);
    }
  }, [token]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function excluir(im: AdminImovel) {
    Alert.alert("Excluir imóvel", `Excluir "${im.titulo}" permanentemente?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir",
        style: "destructive",
        onPress: async () => {
          try {
            await apiFetch(`/api/painel-master/imoveis/${im.id}`, { method: "DELETE", token });
            await carregar();
          } catch (e: any) {
            Alert.alert("Erro", e.message || "Não foi possível excluir.");
          }
        },
      },
    ]);
  }

  if (carregando) return <ActivityIndicator style={{ marginTop: 30 }} color={cores.primaria} />;
  if (erro) return <Text style={styles.erroTexto}>{erro}</Text>;

  return (
    <View>
      {imoveis.map((im) => (
        <TouchableOpacity key={im.id} style={styles.linha} onLongPress={() => excluir(im)}>
          <View style={{ flex: 1 }}>
            <Text style={styles.linhaNome}>{im.titulo}</Text>
            <Text style={styles.linhaSub}>
              {im.proprietario} · {im.endereco}
            </Text>
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );
}

function SecaoFinanceiro({ token }: { token: string | null }) {
  const [dados, setDados] = useState<AdminFinanceiroResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const resposta = await apiFetch<AdminFinanceiroResponse>("/api/painel-master/financeiro", { token });
        setDados(resposta);
      } catch (e: any) {
        setErro(e.message || "Não foi possível carregar.");
      } finally {
        setCarregando(false);
      }
    })();
  }, [token]);

  if (carregando) return <ActivityIndicator style={{ marginTop: 30 }} color={cores.primaria} />;
  if (erro) return <Text style={styles.erroTexto}>{erro}</Text>;
  if (!dados) return null;

  return (
    <View>
      <View style={styles.kpisGrid}>
        <Kpi label="Faturamento bruto" valor={`R$ ${formatarMoeda(dados.faturamento_bruto)}`} cor={cores.sucesso} />
        <Kpi label="Faturamento líquido" valor={`R$ ${formatarMoeda(dados.faturamento_liquido)}`} cor="#0284c7" />
        <Kpi label="Registros" valor={String(dados.total_registros)} cor={cores.aviso} />
        <Kpi label="Usuários c/ lançamento" valor={String(dados.total_usuarios_financas)} cor="#9333ea" />
      </View>

      <Text style={styles.secaoTitulo}>Últimos lançamentos</Text>
      {dados.registros.slice(0, 30).map((r) => (
        <View key={r.id} style={styles.linha}>
          <View style={{ flex: 1 }}>
            <Text style={styles.linhaNome}>{r.imovel || "—"}</Text>
            <Text style={styles.linhaSub}>
              {r.usuario} · {r.data}
            </Text>
          </View>
          <Text style={styles.linhaData}>R$ {formatarMoeda(r.bruto)}</Text>
        </View>
      ))}
    </View>
  );
}

export default function AdminScreen() {
  const { token, user } = useAuth();
  const [secao, setSecao] = useState<Secao>("geral");

  if (!user?.is_admin) {
    return (
      <View style={styles.centro}>
        <Text style={styles.bloqueadoTexto}>Acesso restrito ao Painel Master.</Text>
      </View>
    );
  }

  const abas: { key: Secao; label: string }[] = [
    { key: "geral", label: "Visão geral" },
    { key: "usuarios", label: "Usuários" },
    { key: "imoveis", label: "Imóveis" },
    { key: "financeiro", label: "Financeiro" },
  ];

  return (
    <View style={styles.container}>
      <Text style={styles.titulo}>Painel Master</Text>

      <FlatList
        horizontal
        data={abas}
        keyExtractor={(a) => a.key}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 8, marginBottom: 16 }}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.aba, secao === item.key && styles.abaAtiva]}
            onPress={() => setSecao(item.key)}
          >
            <Text style={[styles.abaTexto, secao === item.key && styles.abaTextoAtivo]}>{item.label}</Text>
          </TouchableOpacity>
        )}
      />

      <FlatList
        data={[{ key: "conteudo" }]}
        keyExtractor={(i) => i.key}
        contentContainerStyle={{ paddingBottom: 40 }}
        renderItem={() => (
          <>
            {secao === "geral" && <SecaoGeral token={token} />}
            {secao === "usuarios" && <SecaoUsuarios token={token} />}
            {secao === "imoveis" && <SecaoImoveis token={token} />}
            {secao === "financeiro" && <SecaoFinanceiro token={token} />}
          </>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: cores.fundo, padding: 20 },
  centro: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  bloqueadoTexto: { textAlign: "center", color: cores.textoMuted, fontSize: 14 },
  titulo: { fontSize: 22, fontWeight: "800", color: cores.textoEscuro, marginBottom: 14 },
  heroAdmin: { backgroundColor: "#7f1d1d", borderRadius: raio.md, padding: 16, marginBottom: 16 },
  heroTitulo: { color: "#fff", fontWeight: "800", fontSize: 15, marginBottom: 6 },
  heroDesc: { color: "#f6cdcd", fontSize: 11.5, lineHeight: 16 },
  aba: { borderWidth: 1, borderColor: cores.borda, borderRadius: raio.pill, paddingVertical: 8, paddingHorizontal: 14, backgroundColor: cores.cardFundo },
  abaAtiva: { backgroundColor: cores.perigo, borderColor: cores.perigo },
  abaTexto: { fontSize: 12, fontWeight: "700", color: cores.textoEscuro },
  abaTextoAtivo: { color: "#fff" },
  erroTexto: { color: cores.perigo, fontWeight: "600", textAlign: "center", marginTop: 20 },
  kpisGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 16 },
  kpiCard: { width: "47%", backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 14, overflow: "hidden", ...sombraCard },
  kpiBarra: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4 },
  kpiLabel: { fontSize: 10.5, fontWeight: "700", color: cores.textoMuted, textTransform: "uppercase", marginBottom: 6 },
  kpiValor: { fontSize: 14.5, fontWeight: "800", color: cores.textoEscuro },
  secaoTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 14, marginBottom: 10 },
  busca: { borderWidth: 1, borderColor: cores.borda, borderRadius: raio.sm, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, marginBottom: 14, backgroundColor: cores.cardFundo, color: cores.textoEscuro },
  linha: { flexDirection: "row", alignItems: "center", backgroundColor: cores.cardFundo, borderRadius: raio.md - 2, padding: 12, marginBottom: 8 },
  linhaNome: { fontWeight: "700", color: cores.textoEscuro, fontSize: 13.5 },
  linhaSub: { fontSize: 11.5, color: "#9ca3af", marginTop: 2 },
  linhaData: { fontSize: 11.5, color: cores.textoMuted },
  badges: { flexDirection: "row", gap: 6 },
  badge: { borderRadius: raio.sm, paddingVertical: 4, paddingHorizontal: 8 },
  badgeTexto: { fontSize: 10, fontWeight: "700" },
  badgeVerde: { backgroundColor: "#dcfce7" },
  badgeRoxo: { backgroundColor: "#f3e8ff" },
  badgeCinza: { backgroundColor: "#f1f5f9" },
});
