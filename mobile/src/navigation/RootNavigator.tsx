import React from "react";
import { View, Text, ActivityIndicator } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { useAuth } from "../contexts/AuthContext";
import { cores } from "../theme";

import LoginScreen from "../screens/LoginScreen";
import DashboardScreen from "../screens/DashboardScreen";
import ImoveisScreen from "../screens/ImoveisScreen";
import FinancasScreen from "../screens/FinancasScreen";
import HubScreen from "../screens/HubScreen";
import EquipeScreen from "../screens/EquipeScreen";
import ProprietarioScreen from "../screens/ProprietarioScreen";
import PerfilScreen from "../screens/PerfilScreen";
import AdminScreen from "../screens/AdminScreen";

const AuthStackNav = createNativeStackNavigator();
const Tabs = createBottomTabNavigator();

function TabIcone({ emoji, focado }: { emoji: string; focado: boolean }) {
  return (
    <View
      style={{
        width: 30,
        height: 30,
        alignItems: "center",
        justifyContent: "center",
        opacity: focado ? 1 : 0.55,
      }}
    >
      <Text style={{ fontSize: 18 }}>{emoji}</Text>
    </View>
  );
}

// Mesma regra de visibilidade de menu usada na sidebar do site
// (app/templates/base_dash.html): Imóveis/Finanças/Hub só pra
// Anfitrião/Proprietário; Dashboard do Proprietário e Equipe só pra quem
// não é ajudante; Painel Master só pra admin.
function AppTabs() {
  const { user } = useAuth();
  const categoria = user?.categoria;
  const podeOperar = categoria === "Anfitrião" || categoria === "Proprietário";
  const ehProprietarioTitular = !user?.e_ajudante && categoria === "Proprietário";
  const podeGerenciarEquipe = !user?.e_ajudante && podeOperar;

  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: cores.primaria,
        tabBarInactiveTintColor: "#9ca3af",
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        tabBarStyle: { borderTopColor: cores.borda, height: 58, paddingBottom: 6 },
      }}
    >
      <Tabs.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{
          tabBarLabel: "Início",
          tabBarIcon: ({ focused }) => <TabIcone emoji="🏠" focado={focused} />,
        }}
      />
      {podeOperar ? (
        <Tabs.Screen
          name="Imoveis"
          component={ImoveisScreen}
          options={{
            tabBarLabel: "Imóveis",
            tabBarIcon: ({ focused }) => <TabIcone emoji="🏢" focado={focused} />,
          }}
        />
      ) : null}
      {podeOperar ? (
        <Tabs.Screen
          name="Financas"
          component={FinancasScreen}
          options={{
            tabBarLabel: "Finanças",
            tabBarIcon: ({ focused }) => <TabIcone emoji="💰" focado={focused} />,
          }}
        />
      ) : null}
      {podeOperar ? (
        <Tabs.Screen
          name="Hub"
          component={HubScreen}
          options={{
            tabBarLabel: "Hub",
            tabBarIcon: ({ focused }) => <TabIcone emoji="💡" focado={focused} />,
          }}
        />
      ) : null}
      {ehProprietarioTitular ? (
        <Tabs.Screen
          name="Proprietario"
          component={ProprietarioScreen}
          options={{
            tabBarLabel: "Proprietário",
            tabBarIcon: ({ focused }) => <TabIcone emoji="📈" focado={focused} />,
          }}
        />
      ) : null}
      {podeGerenciarEquipe ? (
        <Tabs.Screen
          name="Equipe"
          component={EquipeScreen}
          options={{
            tabBarLabel: "Equipe",
            tabBarIcon: ({ focused }) => <TabIcone emoji="👥" focado={focused} />,
          }}
        />
      ) : null}
      {user?.is_admin ? (
        <Tabs.Screen
          name="Admin"
          component={AdminScreen}
          options={{
            tabBarLabel: "Master",
            tabBarIcon: ({ focused }) => <TabIcone emoji="🔐" focado={focused} />,
          }}
        />
      ) : null}
      <Tabs.Screen
        name="Perfil"
        component={PerfilScreen}
        options={{
          tabBarLabel: "Perfil",
          tabBarIcon: ({ focused }) => <TabIcone emoji="👤" focado={focused} />,
        }}
      />
    </Tabs.Navigator>
  );
}

export default function RootNavigator() {
  const { token, carregando } = useAuth();

  if (carregando) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#fff" }}>
        <ActivityIndicator size="large" color={cores.primaria} />
      </View>
    );
  }

  return (
    <NavigationContainer>
      {token ? (
        <AppTabs />
      ) : (
        <AuthStackNav.Navigator screenOptions={{ headerShown: false }}>
          <AuthStackNav.Screen name="Login" component={LoginScreen} />
        </AuthStackNav.Navigator>
      )}
    </NavigationContainer>
  );
}
