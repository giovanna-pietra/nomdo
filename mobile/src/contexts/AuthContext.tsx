import React, {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { apiFetch } from "../api/client";
import { Usuario } from "../types";

const TOKEN_KEY = "@nomdo/token";

interface AuthContextValue {
  token: string | null;
  user: Usuario | null;
  carregando: boolean;
  erro: string | null;
  login: (email: string, senha: string) => Promise<void>;
  logout: () => Promise<void>;
  atualizarUsuario: (user: Usuario) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  // Ao abrir o app, tenta recuperar um token salvo e validar com o backend.
  useEffect(() => {
    (async () => {
      try {
        const tokenSalvo = await AsyncStorage.getItem(TOKEN_KEY);
        if (tokenSalvo) {
          const resposta = await apiFetch<{ user: Usuario }>("/api/auth/me", {
            token: tokenSalvo,
          });
          setToken(tokenSalvo);
          setUser(resposta.user);
        }
      } catch {
        await AsyncStorage.removeItem(TOKEN_KEY);
      } finally {
        setCarregando(false);
      }
    })();
  }, []);

  async function login(email: string, senha: string) {
    setErro(null);
    try {
      const resposta = await apiFetch<{ token: string; user: Usuario }>(
        "/api/auth/login",
        { method: "POST", body: { email, senha } }
      );
      await AsyncStorage.setItem(TOKEN_KEY, resposta.token);
      setToken(resposta.token);
      setUser(resposta.user);
    } catch (e: any) {
      setErro(e.message || "Não foi possível entrar.");
      throw e;
    }
  }

  async function logout() {
    await AsyncStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }

  function atualizarUsuario(novoUser: Usuario) {
    setUser(novoUser);
  }

  return (
    <AuthContext.Provider
      value={{ token, user, carregando, erro, login, logout, atualizarUsuario }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth precisa estar dentro de um <AuthProvider>");
  }
  return context;
}
