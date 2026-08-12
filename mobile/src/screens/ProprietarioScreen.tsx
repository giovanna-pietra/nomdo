import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../api/client";
import { ProprietarioResponse, ImovelLucro } from "../types";
import { cores, raio, sombraCard } from "../theme";

// Espelha app/templates/proprietario_dashboard.html: KPIs do mês,
// "Consolidado — todos os imóveis" e "Lucro por imóvel".
function formatarMoeda(valor: number): string {
  return (valor || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Kpi({ label, valor, cor }: { label: string; valor: string; cor: string }) {
  return (
    <View style={styles.kpiCard}>
      <View style={[styles.kpiIcone, { backgroundColor: cor }]} />
      <Text style={styles.kpiLabel}>{label}</Text>
      <Text style={styles.kpiValor}>R$ {valor}</Text>
    </View>
  );
}

function ImovelCard({ item }: { item: ImovelLucro }) {
  const [aberto, setAberto] = useState(false);
  return (
    <TouchableOpacity style={styles.imovelCard} onPress={() => setAberto(!aberto)} activeOpacity={0.8}>
      <View style={styles.imovelHeader}>
        <View style={styles.imovelIconeCasa}>
          <Text style={{ fontSize: 16 }}>🏠</Text>
        </View>
        <Text style={styles.imovelTitulo} numberOfLines={1}>
          {item.titulo}
        </Text>
        <Text style={styles.imovelLucroMes}>R$ {formatarMoeda(item.lucro_mes)}</Text>
        <Text style={styles.chevron}>{aberto ? "︿" : "﹀"}</Text>
      </View>

      {aberto ? (
        <View style={styles.imovelBody}>
          <View style={styles.linha}>
            <Text style={styles.linhaLabel}>Faturamento do mês</Text>
            <Text style={styles.linhaValor}>R$ {formatarMoeda(item.faturamento_mes)}</Text>
          </View>
          <View style={styles.linha}>
            <Text style={styles.linhaLabel}>Despesas do mês</Text>
            <Text style={styles.linhaValorNegativo}>R$ {formatarMoeda(item.despesas_mes)}</Text>
          </View>
          <View style={styles.divisor} />
          <View style={styles.linha}>
            <Text style={styles.linhaLabel}>Faturamento total (histórico)</Text>
            <Text style={styles.linhaValor}>R$ {formatarMoeda(item.faturamento_total)}</Text>
          </View>
          <View style={styles.linha}>
            <Text style={styles.linhaLabel}>Despesas totais (histórico)</Text>
            <Text style={styles.linhaValorNegativo}>R$ {formatarMoeda(item.despesas_total)}</Text>
          </View>
          <View style={styles.linha}>
            <Text style={styles.linhaLabel}>Lucro total acumulado</Text>
            <Text style={styles.linhaValor}>R$ {formatarMoeda(item.lucro_total)}</Text>
          </View>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

export default function ProprietarioScreen() {
  const { token } = useAuth();
  const [dados, setDados] = useState<ProprietarioResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [bloqueado, setBloqueado] = useState(false);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await apiFetch<ProprietarioResponse>("/api/proprietario/dashboard", { token });
      setDados(resposta);
      setBloqueado(false);
    } catch (e: any) {
      if (e.status === 403) {
        setBloqueado(true);
      } else {
        setErro(e.message || "Não foi possível carregar o dashboard.");
      }
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

  if (bloqueado) {
    return (
      <View style={styles.centro}>
        <Text style={styles.bloqueadoTexto}>O dashboard financeiro é exclusivo da conta Proprietária.</Text>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={{ padding: 20, paddingBottom: 40 }}
      data={dados?.imoveis || []}
      keyExtractor={(i) => String(i.id)}
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
          <Text style={styles.titulo}>Dashboard do Proprietário</Text>
          <Text style={styles.subtitulo}>Referente a {dados?.mes_referencia}</Text>

          {erro ? (
            <View style={styles.alertaErro}>
              <Text style={styles.alertaErroTexto}>{erro}</Text>
            </View>
          ) : null}

          {dados && !dados.tem_imoveis ? (
            <View style={styles.aviso}>
              <Text style={styles.avisoTitulo}>Ainda não há imóveis cadastrados</Text>
            </View>
          ) : dados && !dados.tem_estadias ? (
            <View style={styles.aviso}>
              <Text style={styles.avisoTitulo}>Falta pouco pra desbloquear este dashboard!</Text>
            </View>
          ) : null}

          <View style={styles.kpisGrid}>
            <Kpi label="Faturamento do mês" valor={formatarMoeda(dados?.consolidado.faturamento_mes || 0)} cor="#9333ea" />
            <Kpi label="Despesas do mês" valor={formatarMoeda(dados?.consolidado.despesas_mes || 0)} cor={cores.aviso} />
            <Kpi label="Lucro do mês" valor={formatarMoeda(dados?.consolidado.lucro_mes || 0)} cor={cores.sucesso} />
            <Kpi label="Lucro total acumulado" valor={formatarMoeda(dados?.consolidado.lucro_total || 0)} cor="#0284c7" />
          </View>

          <View style={styles.consolidadoBox}>
            <Text style={styles.consolidadoTitulo}>Consolidado — todos os imóveis</Text>
            <View style={styles.consolidadoLinha}>
              <View>
                <Text style={styles.consolidadoLabel}>Faturamento total</Text>
                <Text style={styles.consolidadoValor}>R$ {formatarMoeda(dados?.consolidado.faturamento_total || 0)}</Text>
              </View>
              <View>
                <Text style={styles.consolidadoLabel}>Despesas totais</Text>
                <Text style={styles.consolidadoValor}>R$ {formatarMoeda(dados?.consolidado.despesas_total || 0)}</Text>
              </View>
              <View>
                <Text style={styles.consolidadoLabel}>Imóveis</Text>
                <Text style={styles.consolidadoValor}>{dados?.imoveis.length || 0}</Text>
              </View>
            </View>
          </View>

          <Text style={styles.secaoTitulo}>🏢 Lucro por imóvel</Text>
        </>
      }
      ListEmptyComponent={<Text style={styles.vazio}>Nenhum imóvel cadastrado ainda.</Text>}
      renderItem={({ item }) => <ImovelCard item={item} />}
      ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: cores.fundo },
  centro: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  bloqueadoTexto: { textAlign: "center", color: cores.textoMuted, fontSize: 14 },
  titulo: { fontSize: 22, fontWeight: "800", color: cores.textoEscuro },
  subtitulo: { color: cores.textoMuted, marginTop: 4, marginBottom: 16, fontSize: 13 },
  alertaErro: { backgroundColor: cores.perigoClaro, borderRadius: raio.sm, padding: 12, marginBottom: 12 },
  alertaErroTexto: { color: "#991b1b", fontWeight: "600" },
  aviso: { backgroundColor: "rgba(245,158,11,0.12)", borderRadius: raio.md, padding: 14, marginBottom: 16 },
  avisoTitulo: { color: "#92400e", fontWeight: "800", fontSize: 14 },
  kpisGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 16 },
  kpiCard: { width: "47%", backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 14, ...sombraCard },
  kpiIcone: { width: 30, height: 30, borderRadius: 9, marginBottom: 8 },
  kpiLabel: { fontSize: 10.5, fontWeight: "700", color: cores.textoMuted, textTransform: "uppercase", marginBottom: 4 },
  kpiValor: { fontSize: 15, fontWeight: "800", color: cores.textoEscuro },
  consolidadoBox: { backgroundColor: cores.primaria, borderRadius: raio.lg, padding: 18, marginBottom: 20 },
  consolidadoTitulo: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontWeight: "700", marginBottom: 12 },
  consolidadoLinha: { flexDirection: "row", justifyContent: "space-between" },
  consolidadoLabel: { color: "rgba(255,255,255,0.75)", fontSize: 11, marginBottom: 4 },
  consolidadoValor: { color: "#fff", fontWeight: "800", fontSize: 15 },
  secaoTitulo: { fontWeight: "800", color: cores.textoEscuro, fontSize: 15, marginBottom: 10 },
  vazio: { color: "#9ca3af", textAlign: "center", marginTop: 20 },
  imovelCard: { backgroundColor: cores.cardFundo, borderRadius: raio.md, padding: 14 },
  imovelHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
  imovelIconeCasa: { width: 32, height: 32, borderRadius: 10, backgroundColor: "#f1f5f9", alignItems: "center", justifyContent: "center" },
  imovelTitulo: { flex: 1, fontWeight: "700", color: cores.textoEscuro, fontSize: 13.5 },
  imovelLucroMes: { fontWeight: "800", color: cores.textoEscuro, fontSize: 13 },
  chevron: { color: "#9ca3af", fontSize: 12, width: 16, textAlign: "center" },
  imovelBody: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: "#f1f5f9" },
  linha: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 5 },
  linhaLabel: { color: cores.textoMuted, fontSize: 12.5 },
  linhaValor: { fontWeight: "700", color: cores.textoEscuro, fontSize: 12.5 },
  linhaValorNegativo: { fontWeight: "700", color: cores.perigo, fontSize: 12.5 },
  divisor: { borderTopWidth: 1, borderTopColor: "#f1f5f9", borderStyle: "dashed", marginVertical: 4 },
});
