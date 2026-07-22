"use client";

import { ArrowDown, ArrowsClockwise, ArrowUp } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api } from "@/lib/api";
import type { TopMover } from "@/lib/types";
import { formatCompact, formatPrice } from "@/lib/utils";

function TokenRow({ token, rank }: { token: TopMover; rank: number }) {
  const isGain = token.price_change_percent >= 0;
  const changeColor = isGain ? "text-[var(--positive)]" : "text-[var(--negative)]";

  return (
    <div className="grid grid-cols-[1.5rem_1fr_auto_auto_auto] items-center gap-x-3 border-b border-[var(--line)] px-4 py-3 last:border-0 hover:bg-[var(--line)]/20 transition-colors">
      <span className="text-[11px] font-mono text-[var(--muted)] text-right">{rank}</span>
      <div className="min-w-0">
        <p className="text-sm font-semibold truncate">
          {token.symbol.replace("USDT", "")}
          <span className="text-[var(--muted)] font-normal">/USDT</span>
        </p>
        <p className="text-[10px] text-[var(--muted)] mt-0.5 font-mono">
          Vol {formatCompact(token.quote_volume)}
        </p>
      </div>
      <div className="text-right hidden sm:block">
        <p className="text-[10px] text-[var(--muted)]">24h H/L</p>
        <p className="text-[11px] font-mono">
          {formatPrice(token.high)} / {formatPrice(token.low)}
        </p>
      </div>
      <div className="text-right">
        <p className="text-[10px] text-[var(--muted)]">Price</p>
        <p className="text-[11px] font-mono">${formatPrice(token.price)}</p>
      </div>
      <div className={`text-right min-w-[4.5rem] ${changeColor}`}>
        <div className="flex items-center justify-end gap-0.5">
          {isGain ? <ArrowUp size={11} weight="bold" /> : <ArrowDown size={11} weight="bold" />}
          <span className="text-sm font-bold font-mono">
            {Math.abs(token.price_change_percent).toFixed(2)}%
          </span>
        </div>
        <p className="text-[10px] font-mono opacity-75">
          {isGain ? "+" : ""}{formatPrice(token.price_change)}
        </p>
      </div>
    </div>
  );
}

export function ScannedTokensConsole() {
  const [tokens, setTokens] = useState<TopMover[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    setError(null);
    try {
      const result = await api.scannedTokens();
      setTokens(result.tokens);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load scanned tokens");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    load();
    const timer = window.setInterval(() => load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  return (
    <AppShell>
      <div className="p-4 sm:p-6 max-w-3xl mx-auto">
        <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-base font-bold tracking-tight">Scanned Tokens</h1>
            <p className="text-[11px] text-[var(--muted)] mt-0.5">
              Binance Futures · 24h change · symbols currently scanned by the bot
            </p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium text-[var(--muted)] hover:text-[var(--text)] transition-colors disabled:opacity-50"
          >
            <ArrowsClockwise size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        <Panel>
          <PanelHeader title={`Scanning ${tokens.length} token${tokens.length === 1 ? "" : "s"}`} />
          {loading ? (
            <div className="flex items-center justify-center py-16 text-[var(--muted)] text-sm">
              Loading…
            </div>
          ) : error ? (
            <div className="px-4 py-8 text-center text-[var(--negative)] text-sm">{error}</div>
          ) : tokens.length === 0 ? (
            <div className="px-4 py-8 text-center text-[var(--muted)] text-sm">
              No tokens are currently running. Start scanning a symbol from Settings or Top Movers.
            </div>
          ) : (
            <div>
              {tokens.map((token, i) => (
                <TokenRow key={token.symbol} token={token} rank={i + 1} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}
