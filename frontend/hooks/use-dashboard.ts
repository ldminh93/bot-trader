"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, getToken } from "@/lib/api";
import { getWsBaseUrl } from "@/lib/runtime-config";
import type {
  BotConfig,
  BotLog,
  MarketSnapshot,
  Trade,
  TradeStats,
  TrendState,
} from "@/lib/types";

const EMPTY_STATS: TradeStats = {
  realized_pnl: 0,
  unrealized_pnl: 0,
  total_profit: 0,
  trades: 0,
  win_rate: 0,
  average_pnl_percent: 0,
  daily: [],
  analytics: {
    by_symbol: [],
    by_side: [],
    by_hour: [],
    by_close_reason: [],
    by_setup_tag: [],
  },
};

function normalizeTrendState(
  value: unknown,
  legacyTrend: unknown,
): TrendState {
  const validStates: TrendState[] = [
    "SIDEWAY",
    "EARLY_UPTREND",
    "CONFIRMED_UPTREND",
    "WEAK_UPTREND",
    "EARLY_DOWNTREND",
    "CONFIRMED_DOWNTREND",
    "WEAK_DOWNTREND",
  ];
  if (typeof value === "string" && validStates.includes(value as TrendState)) {
    return value as TrendState;
  }
  if (value === "UP" || legacyTrend === "UP") return "CONFIRMED_UPTREND";
  if (value === "DOWN" || legacyTrend === "DOWN") return "CONFIRMED_DOWNTREND";
  return "SIDEWAY";
}

function normalizeSnapshot(
  snapshot: MarketSnapshot,
  previous?: MarketSnapshot | null,
): MarketSnapshot {
  const payload = snapshot.payload ?? ({} as MarketSnapshot["payload"]);
  const trendState = normalizeTrendState(payload.trend_state, snapshot.trend);
  const higherState = normalizeTrendState(payload.trend_1h, payload.trend_1h);
  const canReuseHistory = Boolean(
    previous
      && previous.symbol === snapshot.symbol
      && previous.timeframe === snapshot.timeframe,
  );
  return {
    ...snapshot,
    trend: trendState,
    payload: {
      ...payload,
      trend_state: trendState,
      trend_1h: higherState,
      signal: payload.signal ?? "NO_TRADE",
      long_score: payload.long_score ?? 0,
      short_score: payload.short_score ?? 0,
      risk_multiplier: payload.risk_multiplier ?? 0,
      reasons: payload.reasons ?? ["Waiting for a current strategy snapshot"],
      trend_reasons: payload.trend_reasons ?? [],
      higher_timeframe_bias: payload.higher_timeframe_bias,
      regime: payload.regime ?? "MANUAL",
      regime_label: payload.regime_label ?? "Manual",
      regime_notes: payload.regime_notes ?? [],
      confidence_score: payload.confidence_score ?? 0,
      effective_leverage: payload.effective_leverage ?? 0,
      leverage_factor: payload.leverage_factor ?? 1,
      tp_r_multiple: payload.tp_r_multiple ?? 0,
      candles: payload.candles ?? [],
      market_history: payload.market_history
        ?? (canReuseHistory ? previous?.payload.market_history : undefined),
    },
  };
}

export function useDashboard(symbol: string | null) {
  const router = useRouter();
  const selectedSymbol = useRef(symbol);
  selectedSymbol.current = symbol;
  const [config, setConfig] = useState<BotConfig | null>(null);
  const configRef = useRef<BotConfig | null>(null);
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<TradeStats>(EMPTY_STATS);
  const [logs, setLogs] = useState<BotLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    configRef.current = config;
  }, [config]);

  const snapshotMatchesCurrentView = useCallback((next: MarketSnapshot, expectedConfig?: BotConfig | null) => {
    const activeConfig = expectedConfig ?? configRef.current;
    if (next.symbol !== selectedSymbol.current) return false;
    return !activeConfig || next.timeframe === activeConfig.timeframe_signal;
  }, []);

  const refresh = useCallback(async () => {
    if (!symbol) return;
    if (!getToken()) {
      router.push("/login");
      return;
    }
    try {
      const [nextConfig, nextTrades, nextStats, nextLogs] = await Promise.all([
        api.config(symbol),
        api.trades(symbol),
        api.stats(),
        api.logs(),
      ]);
      if (selectedSymbol.current !== symbol) return;
      setConfig(nextConfig);
      configRef.current = nextConfig;
      setTrades(nextTrades);
      setStats(nextStats);
      setLogs(nextLogs);
      try {
        const nextSnapshot = await api.snapshot(symbol);
        if (selectedSymbol.current !== symbol) return;
        if (!snapshotMatchesCurrentView(nextSnapshot, nextConfig)) {
          setSnapshot(null);
          return;
        }
        setSnapshot((current) => normalizeSnapshot(nextSnapshot, current));
      } catch {
        setSnapshot(null);
      }
      setError("");
    } catch (reason) {
      if (selectedSymbol.current !== symbol) return;
      setError(reason instanceof Error ? reason.message : "Unable to load dashboard");
    } finally {
      if (selectedSymbol.current === symbol) setLoading(false);
    }
  }, [router, symbol]);

  useEffect(() => {
    if (!symbol) {
      setConfig(null);
      setSnapshot(null);
      setTrades([]);
      setLogs([]);
      setLoading(false);
      setError("");
      return;
    }
    setConfig(null);
    setSnapshot(null);
    setTrades([]);
    setLogs([]);
    setLoading(true);
    setError("");
    void refresh();
    const timer = window.setInterval(refresh, 10_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    let socket: WebSocket | null = null;

    function connect() {
      const token = getToken();
      if (!token) return;
      socket?.close();
      const base = getWsBaseUrl();
      socket = new WebSocket(`${base}/bot/?token=${token}`);
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as { event: string; payload: MarketSnapshot | Trade | BotLog };
        if (event.event === "snapshot") {
          const next = event.payload as MarketSnapshot;
          if (!snapshotMatchesCurrentView(next)) return;
          setSnapshot((current) => {
            if (!snapshotMatchesCurrentView(next)) return current;
            return normalizeSnapshot(next, current);
          });
        }
        if (event.event === "position") {
          const trade = event.payload as Trade;
          if (trade.symbol !== selectedSymbol.current) return;
          setTrades((current) => {
            if (trade.symbol !== selectedSymbol.current) return current;
            return [trade, ...current.filter((item) => item.id !== trade.id)];
          });
        }
        if (event.event === "log") {
          const log = event.payload as BotLog;
          if (log.symbol !== selectedSymbol.current) return;
          setLogs((current) => {
            if (log.symbol !== selectedSymbol.current) return current;
            return [log, ...current].slice(0, 200);
          });
        }
      };
    }

    connect();
    window.addEventListener("auth-token-refreshed", connect);
    return () => {
      window.removeEventListener("auth-token-refreshed", connect);
      socket?.close();
    };
  }, [symbol]);

  const visibleConfig = symbol && config?.symbol === symbol ? config : null;
  const visibleSnapshot = symbol && snapshot?.symbol === symbol ? snapshot : null;
  const visibleTrades = symbol ? trades.filter((trade) => trade.symbol === symbol) : [];
  const visibleLogs = symbol ? logs.filter((log) => log.symbol === symbol) : [];

  return {
    config: visibleConfig,
    setConfig,
    setSnapshot,
    snapshot: visibleSnapshot,
    trades: visibleTrades,
    stats,
    logs: visibleLogs,
    loading,
    error,
    refresh,
  };
}
