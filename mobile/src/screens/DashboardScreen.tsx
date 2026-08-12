import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
  TouchableOpacity,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { DashboardResponse } from "../types";
import { cores, raio, sombraCard } from "../theme";

// Espelha app/templates/dashboard.html: KPIs de Reservas Ativas, Média de
// Ocupação, Faturamento Total, Imóvel Mais/Menos Procurado + seção de
// Insights Inteligentes + painel de Performance Geral.
function Kpi({ label, valor, sub, cor }: { label: string; valor: string; sub: string; cor: string }) {
  return (
    <View style={styles.kpiCard}>
      <View style={[styles.kpiBarra, { backgroundColor: cor }]} />
      <Text style={styles.kpiLabel}>{label}</Text>
      <Text style={styles.kpiValor} numberOfLines={1}>{valor}</Text>
      <Text style={styles.kpiSub}>{sub}</Text>
    </View>
  );
}

export default function DashboardScreen() {
  const { user } = useAuth();
  const navigation = useNavigation<any>();
  const { token, logout } = useAuth();
  const [dados, setDados] = useState<DashboardResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await apiFetch<DashboardResponse>("/api/dashboard", { token });
      setDados(resposta);
    } catch (e: any) {
      setErro(e.message || "Não foi possível carregar o dashboard.");
    } finally {
      setCarregando(false);
      setAtualizando(false);
    }
  }, [token]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  if (carregando) {
    return (
      <View style={styles.centro}>
        <ActivityIndicator size="large" color={cores.primaria} />
      </View>
    );
  }

  const stats = dados?.stats;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ padding: 20, paddingBottom: 40 }}
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
      <Text style={styles.saudacao}>Olá, {user?.nome?.split(" ")[0]}</Text>
      <Text style={styles.titulo}>Dashboard Nomdo</Text>
      <Text style={styles.subtitulo}>Dashboard Inteligente</Text>

      {erro ? (
        <View style={styles.alertaErro}>
          <Text style={styles.alertaErroTexto}>{erro}</Text>
        </View>
      ) : null}

      {dados && !dados.dashboard_desbloqueado ? (
        <View style={styles.aviso}>
          <Text style={styles.avisoTitulo}>Falta pouco pra desbloquear seu dashboard!</Text>
          <Text style={styles.avisoTexto}>
            {dados.tem_imoveis
              ? "Cadastre pelo menos uma estadia pra liberar as métricas do dashboard."
              : "Cadastre seu primeiro imóvel pra começar a usar o dashboard."}
          </Text>
          {!dados.tem_imoveis ? (
            <TouchableOpacity
              style={styles.botaoAviso}
              onPress={() => navigation.navigate("Imoveis")}
            >
              <Text style={styles.botaoAvisoTexto}>Cadastrar Imóvel</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      {stats ? (
        <View style={styles.kpisGrid}>
          <Kpi
            label="Reservas Ativas"
            valor={String(stats.reservas_ativas)}
            sub="Reservas em andamento"
            cor={cores.sucesso}
          />
          <Kpi
            label="Média de Ocupação"
            valor={`${stats.media_ocupacao}%`}
            sub="Média geral dos imóveis"
            cor={cores.aviso}
          />
          <Kpi
            label="Faturamento Total"
            valor={`R$ ${stats.faturamento_total}`}
            sub="Receita consolidada"
            cor={cores.primaria}
          />
          <Kpi
            label="Imóvel Mais Procurado"
            valor={stats.imovel_mais_procurado || "—"}
            sub="Melhor performance"
            cor="#e11d48"
          />
          {stats.imovel_menos_procurado ? (
            <Kpi
              label="Imóvel Menos Procurado"
              valor={stats.imovel_menos_procurado}
              sub="Menor ocupação"
              cor="#9333ea"
            />
          ) : null}
        </View>
      ) : null}

      {stats?.imovel_mais_procurado || stats?.media_ocupacao ? (
        <View style={styles.insightsBox}>
          <Text style={styles.insightsTitulo}>✨ Insights Inteligentes</Text>

          {stats?.imovel_mais_procurado ? (
            <View style={styles.insightLinha}>
              <Text style={styles.insightIcone}>🏆</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.insightTitulo}>Melhor imóvel do mês</Text>
                <Text style={styles.insightTexto}>
                  {stats.imovel_mais_procurado} teve a maior procura.
                </Text>
              </View>
            </View>
          ) : null}

          <View style={styles.insightLinha}>
            <Text style={styles.insightIcone}>📊</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.insightTitulo}>Ocupação média</Text>
              <Text style={styles.insightTexto}>
                Seus imóveis estão com média de {stats?.media_ocupacao}% de ocupação.
              </Text>
            </View>
          </View>

          <View style={styles.insightLinha}>
            <Text style={styles.insightIcone}>💰</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.insightTitulo}>Receita acumulada</Text>
              <Text style={styles.insightTexto}>
                Seu faturamento consolidado chegou em R$ {stats?.faturamento_total}.
              </Text>
            </View>
          </View>
        </View>
      ) : null}

      {stats ? (
        <View style={styles.performanceBox}>
          <Text style={styles.performanceTitulo}>Performance Geral</Text>
          <View style={styles.performanceLinha}>
            <View style={{ flex: 1 }}>
              <Text style={styles.performanceLabel}>Ocupação Geral</Text>
              <Text style={styles.performanceValor}>{stats.media_ocupacao}%</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.performanceLabel}>Receita Total</Text>
              <Text style={styles.performanceValor}>R$ {stats.faturamento_total}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.performanceLabel}>RevPAR</Text>
              <Text style={styles.performanceValor}>R$ {stats.revpar}</Text>
            </View>
          </View>
          <Text style={styles.performanceTag}>✓ Sistema operando normalmente</Text>
        </View>
      ) : null}

      <TouchableOpacity style={styles.botaoSair} onPress={logout}>
        <Text style={styles.botaoSairTexto}>Sair</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: cores.fundo },
  centro: { flex: 1, alignItems: "center", justifyContent: "center" },
  saudacao: { color: cores.textoMuted, fontSize: 14 },
  titulo: { fontSize: 24, fontWeight: "800", color: cores.textoEscuro, marginTop: 4 },
  subtitulo: { fontSize: 13, color: cores.textoMuted, marginBottom: 20 },
  alertaErro: {
    backgroundColor: cores.perigoClaro,
    borderRadius: raio.sm,
    padding: 12,
    marginBottom: 16,
  },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  aviso: {
    backgroundColor: "rgba(245,158,11,0.12)",
    borderRadius: raio.md,
    padding: 16,
    marginBottom: 20,
  },
  avisoTitulo: { color: "#92400e", fontWeight: "800", fontSize: 15, marginBottom: 4 },
  avisoTexto: { color: "#92400e", fontWeight: "500" },
  botaoAviso: {
    backgroundColor: cores.primaria,
    borderRadius: raio.sm,
    paddingVertical: 10,
    alignItems: "center",
    marginTop: 12,
  },
  botaoAvisoTexto: { color: "#fff", fontWeight: "700" },
  kpisGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    marginBottom: 20,
  },
  kpiCard: {
    width: "47%",
    backgroundColor: cores.cardFundo,
    borderRadius: raio.lg,
    padding: 16,
    overflow: "hidden",
    ...sombraCard,
  },
  kpiBarra: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4 },
  kpiLabel: {
    fontSize: 11,
    fontWeight: "700",
    color: cores.textoMuted,
    textTransform: "uppercase",
    marginBottom: 6,
  },
  kpiValor: { fontSize: 17, fontWeight: "800", color: cores.textoEscuro },
  kpiSub: { fontSize: 10.5, color: "#9ca3af", marginTop: 3 },
  insightsBox: {
    backgroundColor: cores.cardFundo,
    borderRadius: raio.lg,
    padding: 16,
    marginBottom: 20,
    ...sombraCard,
  },
  insightsTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 15, marginBottom: 12 },
  insightLinha: { flexDirection: "row", gap: 10, marginBottom: 12, alignItems: "flex-start" },
  insightIcone: { fontSize: 18 },
  insightTitulo: { fontWeight: "700", color: cores.textoEscuro, fontSize: 13 },
  insightTexto: { color: cores.textoMuted, fontSize: 12.5, marginTop: 2 },
  performanceBox: {
    backgroundColor: cores.primaria,
    borderRadius: raio.lg,
    padding: 18,
    marginBottom: 24,
  },
  performanceTitulo: { color: "rgba(255,255,255,0.8)", fontWeight: "700", fontSize: 12, marginBottom: 12, textTransform: "uppercase", letterSpacing: 0.5 },
  performanceLinha: { flexDirection: "row", gap: 8 },
  performanceLabel: { color: "rgba(255,255,255,0.75)", fontSize: 10.5, marginBottom: 4 },
  performanceValor: { color: "#fff", fontWeight: "800", fontSize: 14 },
  performanceTag: { color: "rgba(255,255,255,0.85)", fontSize: 11.5, marginTop: 14, fontWeight: "600" },
  botaoSair: {
    alignSelf: "center",
    paddingVertical: 10,
    paddingHorizontal: 24,
  },
  botaoSairTexto: { color: cores.perigo, fontWeight: "700" },
});
