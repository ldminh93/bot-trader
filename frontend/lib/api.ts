import type {
  BacktestResult,
  BotConfig,
  BotLog,
  DiscordAlertConfig,
  KillSwitchResult,
  LiveSyncHealth,
  MarketSnapshot,
  OpportunityItem,
  Trade,
  TradeStats,
} from "./types";
import { getApiBaseUrl } from "./runtime-config";

export function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function clearSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return null;

  if (!refreshPromise) {
    const apiUrl = getApiBaseUrl();
    refreshPromise = fetch(`${apiUrl}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const body = (await response.json()) as { access?: string };
        if (!body.access) return null;
        localStorage.setItem("access_token", body.access);
        window.dispatchEvent(new Event("auth-token-refreshed"));
        return body.access;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  allowRefresh = true,
): Promise<T> {
  const apiUrl = getApiBaseUrl();
  const token = getToken();
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    cache: "no-store",
  });

  if (response.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      return request<T>(path, options, false);
    }
    clearSession();
    if (typeof window !== "undefined") {
      window.location.replace("/login");
    }
    throw new Error("Your session has expired. Please sign in again.");
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail ?? body.message ?? "Request failed");
  }
  return body as T;
}

export const api = {
  async login(email: string, password: string) {
    const result = await request<{ access: string; refresh: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: email.toLowerCase(), password }),
    });
    localStorage.setItem("access_token", result.access);
    localStorage.setItem("refresh_token", result.refresh);
    return result;
  },
  register: (email: string, password: string) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  config: (symbol: string) => request<BotConfig>(`/bot/config?symbol=${symbol}`),
  configs: () => request<BotConfig[]>("/bot/config"),
  addConfig: (symbol: string, copyFromSymbol?: string) =>
    request<BotConfig>("/bot/config", {
      method: "POST",
      body: JSON.stringify({
        symbol,
        copy_from_symbol: copyFromSymbol,
        start_scanning: false,
      }),
    }),
  removeConfig: (symbol: string) =>
    request<void>(`/bot/config?symbol=${encodeURIComponent(symbol)}`, { method: "DELETE" }),
  saveConfig: (body: Partial<BotConfig>) =>
    request<BotConfig>("/bot/config", { method: "PUT", body: JSON.stringify(body) }),
  start: (symbol: string) =>
    request<BotConfig>("/bot/start", { method: "POST", body: JSON.stringify({ symbol }) }),
  stop: (symbol: string) =>
    request<BotConfig>("/bot/stop", { method: "POST", body: JSON.stringify({ symbol }) }),
  closePosition: (symbol: string) =>
    request<Trade>("/bot/close-position", { method: "POST", body: JSON.stringify({ symbol }) }),
  liveSync: () => request<LiveSyncHealth>("/bot/live-sync"),
  killSwitch: () => request<KillSwitchResult>("/bot/kill-switch", { method: "POST" }),
  backtest: (symbol: string, limit = 320) =>
    request<BacktestResult>("/bot/backtest", { method: "POST", body: JSON.stringify({ symbol, limit }) }),
  snapshot: (symbol: string) => request<MarketSnapshot>(`/market/snapshot?symbol=${symbol}`),
  opportunities: () => request<OpportunityItem[]>("/market/opportunities"),
  trades: (symbol?: string) => request<Trade[]>(`/trades${symbol ? `?symbol=${symbol}` : ""}`),
  exportReplay: (tradeId: number) =>
    request<{ message: string }>("/trades/export-replay", { method: "POST", body: JSON.stringify({ trade_id: tradeId }) }),
  stats: () => request<TradeStats>("/trades/stats"),
  logs: () => request<BotLog[]>("/logs"),
  saveCredential: (apiKey: string, apiSecret: string) =>
    request("/binance/credentials", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret, is_active: true }),
    }),
  testConnection: () => request<{ connected: boolean; message: string }>("/binance/connection-test"),
  binanceBalance: () => request<{ balance: number }>("/binance/balance"),
  discordAlerts: () => request<DiscordAlertConfig>("/alerts/discord"),
  saveDiscordAlerts: (body: Partial<DiscordAlertConfig> & { webhook_url?: string }) =>
    request<DiscordAlertConfig>("/alerts/discord", { method: "PUT", body: JSON.stringify(body) }),
  testDiscordAlerts: () => request<{ message: string }>("/alerts/discord", { method: "POST" }),
};
