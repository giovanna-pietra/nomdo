import { API_BASE_URL } from "../config";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/**
 * Cliente HTTP simples (fetch) pro backend Flask.
 * Sempre manda o token (quando existir) no header Authorization.
 */
export async function apiFetch<T = any>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PUT" | "DELETE";
    body?: any;
    token?: string | null;
  } = {}
): Promise<T> {
  const { method = "GET", body, token } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  const data = isJson ? await response.json() : null;

  if (!response.ok) {
    const mensagem = data?.erro || data?.message || `Erro ${response.status}`;
    throw new ApiError(mensagem, response.status);
  }

  return data as T;
}
