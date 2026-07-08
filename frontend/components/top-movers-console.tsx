"use client";

import { ArrowDown, ArrowUp, ArrowsClockwise } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api } from "@/lib/api";
import type { TopMover, TopMoversResult } from "@/lib/types";
import { formatCompact, formatNumber } from "@/lib/utils";

type Tab = "gainers" | "losers";

function readMoversConfig() {
  if (typeof window === "undefined") return { showGainers: true, showLosers: true };
  try {
    const stored = localStorage.getItem("top_movers_config");
    if (!stored) return { showGainers: true, showLosers: true };
    const parsed = JSON.parse(stored) as { showGainers?: boolean; showLosers?: boolean };
    return {
      showGainers: parsed.showGainers !== false,
      showLosers: parsed.showLosers !== false,
    };
  } catch {
    return { showGainers: true, showLosers: true };
  }
}

function MoverRow({ mover, rank }: { mover: TopMover; rank: number }) {
  const isGain = mover.price_change_percent >= 0;
  const changeColor = isGain ? "text-[var(--positive)]" : "text-[var(--negative)]";

  return (
    <div className="grid grid-cols-[1.5rem_1fr_auto_auto_auto] items-center gap-x-3 border-b border-[var(--line)] px-4 py-3 last:border-0 hover:bg-[var(--line)]/20 transition-colors">
      <span className="text-[11px] font-mono text-[var(--muted)] text-right">{rank}</span>
      <div className="min-w-0">
        <p className="text-sm font-semibold truncate">
          {mover.symbol.replace("USDT", "")}
          <span className="text-[var(--muted)] font-normal">/USDT</span>
        </p>
        <p className="text-[10px] text-[var(--muted)] mt-0.5 font-mono">
          Vol {formatCompact(mover.quote_volume)}
        </p>
      </div>
      <div className="text-right hidden sm:block">
        <p className="text-[10px] text-[var(--muted)]">24h H/L</p>
        <p className="text-[11px] font-mono">
          {formatNumber(mover.high)} / {formatNumber(mover.low)}
        </p>
      </div>
      <div className="text-right">
        <p className="text-[10px] text-[var(--muted)]">Price</p>
        <p className="text-[11px] font-mono">${formatNumber(mover.price)}</p>
      </div>
      <div className={`text-right min-w-[4.5rem] ${changeColor}`}>
        <div className="flex items-center justify-end gap-0.5">
          {isGain ? <ArrowUp size={11} weight="bold" /> : <ArrowDown size={11} weight="bold" />}
          <span className="text-sm font-bold font-mono">
            {Math.abs(mover.price_change_percent).toFixed(2)}%
          </span>
        </div>
        <p className="text-[10px] font-mono opacity-75">
          {isGain ? "+" : ""}{formatNumber(mover.price_change)}
        </p>
      </div>
    </div>
  );
}

export function TopMoversConsole() {
  const [data, setData] = useState<TopMoversResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(20);
  const [refreshing, setRefreshing] = useState(false);
  const [showGainers, setShowGainers] = useState(true);
  const [showLosers, setShowLosers] = useState(true);
  const [tab, setTab] = useState<Tab>("gainers");

  useEffect(() => {
    const cfg = readMoversConfig();
    setShowGainers(cfg.showGainers);
    setShowLosers(cfg.showLosers);
    // Auto-select the first enabled tab
    if (!cfg.showGainers && cfg.showLosers) setTab("losers");
    else setTab("gainers");
  }, []);

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    setError(null);
    try {
      const result = await api.topMovers(limit);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load top movers");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [limit]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const rows = data ? data[tab] : [];

  return (
    <AppShell>
      <div className="p-4 sm:p-6 max-w-3xl mx-auto">
        <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-base font-bold tracking-tight">Top Movers</h1>
            <p className="text-[11px] text-[var(--muted)] mt-0.5">Binance Futures · 24h change · USDT pairs</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-xs font-medium text-[var(--text)] focus:outline-none"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              {[10, 20, 30, 50].map((n) => (
                <option key={n} value={n}>Top {n}</option>
              ))}
            </select>
            <button
              onClick={() => load(true)}
              disabled={refreshing}
              className="flex items-center gap-1.5 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium text-[var(--muted)] hover:text-[var(--text)] transition-colors disabled:opacity-50"
            >
              <ArrowsClockwise size={13} className={refreshing ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </div>

        {!showGainers && !showLosers ? (
          <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-4 py-8 text-center text-sm text-[var(--muted)]">
            Both Gainers and Losers lists are disabled.{" "}
            <a href="/settings" className="text-[var(--accent)] underline underline-offset-2">Enable them in Settings.</a>
          </div>
        ) : (
          <>
            {(showGainers || showLosers) && (
              <div className="flex gap-1 mb-4 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] p-1 w-fit">
                {showGainers && (
                  <button
                    onClick={() => setTab("gainers")}
                    className={`flex items-center gap-1.5 rounded-[calc(var(--radius)-2px)] px-4 py-1.5 text-xs font-semibold capitalize transition-colors ${
                      tab === "gainers"
                        ? "bg-[var(--positive)]/15 text-[var(--positive)]"
                        : "text-[var(--muted)] hover:text-[var(--text)]"
                    }`}
                  >
                    <ArrowUp size={12} weight="bold" />
                    Gainers
                  </button>
                )}
                {showLosers && (
                  <button
                    onClick={() => setTab("losers")}
                    className={`flex items-center gap-1.5 rounded-[calc(var(--radius)-2px)] px-4 py-1.5 text-xs font-semibold capitalize transition-colors ${
                      tab === "losers"
                        ? "bg-[var(--negative)]/15 text-[var(--negative)]"
                        : "text-[var(--muted)] hover:text-[var(--text)]"
                    }`}
                  >
                    <ArrowDown size={12} weight="bold" />
                    Losers
                  </button>
                )}
              </div>
            )}
            <Panel>
              <PanelHeader
                title={tab === "gainers" ? `Top ${limit} Gainers` : `Top ${limit} Losers`}
              />
              {loading ? (
                <div className="flex items-center justify-center py-16 text-[var(--muted)] text-sm">
                  Loading…
                </div>
              ) : error ? (
                <div className="px-4 py-8 text-center text-[var(--negative)] text-sm">{error}</div>
              ) : rows.length === 0 ? (
                <div className="px-4 py-8 text-center text-[var(--muted)] text-sm">No data available</div>
              ) : (
                <div>
                  {rows.map((mover, i) => (
                    <MoverRow key={mover.symbol} mover={mover} rank={i + 1} />
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}
      </div>
    </AppShell>
  );
}
