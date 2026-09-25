"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import type { AnalyticsBucket, BlockReasonStat, SymbolAnalyticsBucket, TradeStats } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

const EMPTY_ANALYTICS: TradeStats["analytics"] = {
  by_symbol: [],
  by_side: [],
  by_hour: [],
  by_close_reason: [],
  by_setup_tag: [],
  by_grade: [],
};

export function AnalyticsConsole() {
  const [analytics, setAnalytics] = useState<TradeStats["analytics"]>(EMPTY_ANALYTICS);
  const [blockReasons, setBlockReasons] = useState<BlockReasonStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const stats = await api.stats();
      setAnalytics(stats.analytics);
      setBlockReasons(stats.block_reasons);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load analytics");
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, 10_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return (
    <AppShell>
      <header className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)]/95 px-4 py-4 backdrop-blur md:px-6">
        <h1 className="text-lg font-bold">Analytics</h1>
        <p className="mt-1 text-xs text-[var(--muted)]">Journal, setup tags, and timing breakdowns across all trades</p>
      </header>

      <div className="overflow-x-auto p-4 md:p-6">
        {error && (
          <div className="mb-4 rounded-[var(--radius)] border border-[var(--negative)]/40 bg-[var(--negative)]/10 p-3 text-sm text-[#ff9b9b]">
            {error}
          </div>
        )}
        {loading ? (
          <AnalyticsSkeleton />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
              <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                <span>By symbol</span>
                <span className="normal-case font-normal">Sorted by total PnL — which tokens to keep, trim, or drop</span>
              </div>
              <SymbolDetailTable rows={analytics.by_symbol} />
            </div>
            <AnalyticsBlock title="By side" rows={analytics.by_side} filterKey="side" />
            <AnalyticsBlock title="By close reason" rows={analytics.by_close_reason} filterKey="close_reason" />
            <AnalyticsBlock title="By grade" rows={analytics.by_grade} filterKey="grade" />
            <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
              <div className="border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Best entry hour
                <span className="ml-2 normal-case font-normal">UTC — hover cells for details</span>
              </div>
              <HourHeatmap rows={analytics.by_hour} />
            </div>
            <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
              <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                <span>Setup tag P&L</span>
                <span className="normal-case font-normal">Sorted by total PnL</span>
              </div>
              <TagPnlTable rows={analytics.by_setup_tag} />
            </div>
            <BlockReasonBlock rows={blockReasons} />
          </div>
        )}
      </div>
    </AppShell>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {[0, 1, 2, 3].map((item) => <div key={item} className="h-48 animate-pulse rounded-[var(--radius)] bg-[var(--surface)]" />)}
    </div>
  );
}

function tradesFilterHref(params: Record<string, string>) {
  return `/trades?${new URLSearchParams(params).toString()}`;
}

function HourHeatmap({ rows }: { rows: AnalyticsBucket[] }) {
  const router = useRouter();
  const byHour = new Map(rows.map((r) => [r.label, r]));
  return (
    <div>
      <div className="grid grid-cols-12 gap-0.5 p-3">
        {Array.from({ length: 24 }, (_, h) => {
          const key = `${String(h).padStart(2, "0")}:00`;
          const row = byHour.get(key);
          const wr = row ? row.win_rate : -1;
          let bg = "bg-[var(--surface-raised)]";
          if (wr >= 60) bg = "bg-[var(--positive)]/40";
          else if (wr >= 45) bg = "bg-[var(--positive)]/15";
          else if (wr >= 0 && wr < 45) bg = "bg-[var(--negative)]/20";
          return (
            <div
              key={h}
              role={row ? "button" : undefined}
              onClick={row ? () => router.push(tradesFilterHref({ hour: String(h).padStart(2, "0") })) : undefined}
              title={row
                ? `${key} — ${row.trades} trades, ${row.win_rate.toFixed(0)}% WR, ${row.realized_pnl >= 0 ? "+" : ""}${row.realized_pnl.toFixed(2)} USDT — click to filter trades`
                : `${key} — no trades`}
              className={`${bg} flex flex-col items-center justify-center rounded py-1.5 text-center ${row ? "cursor-pointer hover:opacity-80" : ""}`}
            >
              <span className="text-[9px] font-semibold text-[var(--text)]">{String(h).padStart(2, "0")}</span>
              {row ? <span className="text-[8px] text-[var(--muted)]">{row.trades}</span> : null}
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--line)] px-3 py-2 text-[10px] text-[var(--muted)]">
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--positive)]/40" /> ≥60% WR</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--positive)]/15" /> 45–60%</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--negative)]/20" /> &lt;45%</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--surface-raised)]" /> no data</span>
      </div>
    </div>
  );
}

function formatHoldTime(minutes: number) {
  if (!minutes) return "-";
  if (minutes < 60) return `${minutes.toFixed(0)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

function WinRateCell({ value }: { value: number }) {
  return (
    <span className={value >= 50 ? "text-[var(--positive)]" : "text-[var(--negative)]"}>
      {value.toFixed(0)}%
    </span>
  );
}

function PnlCell({ value }: { value: number }) {
  return (
    <span className={`font-mono ${value >= 0 ? "text-[var(--positive)]" : "text-[var(--negative)]"}`}>
      {value >= 0 ? "+" : ""}{value.toFixed(2)}
    </span>
  );
}

function SymbolDetailTable({ rows }: { rows: SymbolAnalyticsBucket[] }) {
  const router = useRouter();
  const sorted = [...rows].sort((a, b) => b.realized_pnl - a.realized_pnl);
  if (!sorted.length) return <div className="grid min-h-24 place-items-center text-xs text-[var(--muted)]">No symbol data yet.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
          <tr className="border-b border-[var(--line)]">
            <th className="px-3 py-2 text-left">Symbol</th>
            <th className="px-3 py-2 text-right">Trades</th>
            <th className="px-3 py-2 text-right">Win %</th>
            <th className="px-3 py-2 text-right" title="Win rate over the last 20 trades, vs. lifetime — shows whether the edge is fresh or stale">Recent win %</th>
            <th className="px-3 py-2 text-right">PnL</th>
            <th className="px-3 py-2 text-right" title="Gross wins ÷ gross losses. Below 1 means losses outweigh wins.">Profit factor</th>
            <th className="px-3 py-2 text-right" title="Average winning trade / average losing trade">Avg W / L</th>
            <th className="px-3 py-2 text-right" title="Single best and worst closed trade">Best / worst</th>
            <th className="px-3 py-2 text-right">Long PnL</th>
            <th className="px-3 py-2 text-right">Short PnL</th>
            <th className="px-3 py-2 text-right">Avg hold</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={row.label}
              onClick={() => router.push(tradesFilterHref({ symbol: row.label }))}
              className="cursor-pointer border-b border-[var(--line)] last:border-0 hover:bg-[var(--surface-raised)]"
            >
              <td className="px-3 py-2 font-mono text-[10px]">{row.label}</td>
              <td className="px-3 py-2 text-right text-[var(--muted)]">{row.trades}</td>
              <td className="px-3 py-2 text-right"><WinRateCell value={row.win_rate} /></td>
              <td className="px-3 py-2 text-right">
                <WinRateCell value={row.recent_win_rate} />
                <span className="ml-1 text-[var(--muted)]">({row.recent_trades})</span>
              </td>
              <td className="px-3 py-2 text-right font-semibold"><PnlCell value={row.realized_pnl} /></td>
              <td className="px-3 py-2 text-right font-mono">
                {row.profit_factor === null ? (row.average_win > 0 ? "∞" : "-") : row.profit_factor.toFixed(2)}
              </td>
              <td className="px-3 py-2 text-right font-mono">
                <span className="text-[var(--positive)]">+{row.average_win.toFixed(2)}</span>
                {" / "}
                <span className="text-[var(--negative)]">{row.average_loss.toFixed(2)}</span>
              </td>
              <td className="px-3 py-2 text-right font-mono">
                <span className="text-[var(--positive)]">+{row.best_trade.toFixed(2)}</span>
                {" / "}
                <span className="text-[var(--negative)]">{row.worst_trade.toFixed(2)}</span>
              </td>
              <td className="px-3 py-2 text-right">
                {row.long_trades ? (
                  <>
                    <PnlCell value={row.long_pnl} /> <span className="text-[var(--muted)]">({row.long_trades})</span>
                  </>
                ) : (
                  <span className="text-[var(--muted)]">-</span>
                )}
              </td>
              <td className="px-3 py-2 text-right">
                {row.short_trades ? (
                  <>
                    <PnlCell value={row.short_pnl} /> <span className="text-[var(--muted)]">({row.short_trades})</span>
                  </>
                ) : (
                  <span className="text-[var(--muted)]">-</span>
                )}
              </td>
              <td className="px-3 py-2 text-right text-[var(--muted)]">{formatHoldTime(row.avg_hold_minutes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TagPnlTable({ rows }: { rows: AnalyticsBucket[] }) {
  const router = useRouter();
  const sorted = [...rows].sort((a, b) => b.realized_pnl - a.realized_pnl).slice(0, 15);
  if (!sorted.length) return <div className="grid min-h-24 place-items-center text-xs text-[var(--muted)]">No tag data yet.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
          <tr className="border-b border-[var(--line)]">
            <th className="px-3 py-2 text-left">Tag</th>
            <th className="px-3 py-2 text-right">Trades</th>
            <th className="px-3 py-2 text-right">Win %</th>
            <th className="px-3 py-2 text-right">PnL</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={row.label}
              onClick={() => router.push(tradesFilterHref({ tag: row.label }))}
              className="cursor-pointer border-b border-[var(--line)] last:border-0 hover:bg-[var(--surface-raised)]"
            >
              <td className="max-w-[200px] truncate px-3 py-2 font-mono text-[10px]">{row.label}</td>
              <td className="px-3 py-2 text-right text-[var(--muted)]">{row.trades}</td>
              <td className="px-3 py-2 text-right">
                <div className="flex items-center justify-end gap-1.5">
                  <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--surface-raised)]">
                    <div
                      className={`h-full rounded-full ${row.win_rate >= 50 ? "bg-[var(--positive)]" : "bg-[var(--negative)]"}`}
                      style={{ width: `${Math.min(100, row.win_rate)}%` }}
                    />
                  </div>
                  <span className={row.win_rate >= 50 ? "text-[var(--positive)]" : "text-[var(--negative)]"}>
                    {row.win_rate.toFixed(0)}%
                  </span>
                </div>
              </td>
              <td className={`px-3 py-2 text-right font-mono font-semibold ${row.realized_pnl >= 0 ? "text-[var(--positive)]" : "text-[var(--negative)]"}`}>
                {row.realized_pnl >= 0 ? "+" : ""}{row.realized_pnl.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalyticsBlock({
  title,
  rows,
  filterKey,
}: {
  title: string;
  rows: AnalyticsBucket[];
  filterKey?: "side" | "close_reason" | "grade";
}) {
  const router = useRouter();
  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)]">
      <div className="border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
        {title}
      </div>
      <div className="grid">
        {(rows.length ? rows.slice(0, 5) : [{ label: "No data", trades: 0, win_rate: 0, realized_pnl: 0, average_realized_pnl: 0 }]).map((row) => (
          <div
            key={row.label}
            onClick={filterKey && row.trades ? () => router.push(tradesFilterHref({ [filterKey]: row.label })) : undefined}
            className={`grid grid-cols-[1.5fr_0.6fr_0.7fr_0.8fr] gap-2 border-b border-[var(--line)] px-3 py-2 text-xs last:border-0 ${
              filterKey && row.trades ? "cursor-pointer hover:bg-[var(--surface-raised)]" : ""
            }`}
          >
            <span className="truncate">{row.label}</span>
            <span className="font-mono text-[var(--muted)]">{row.trades}</span>
            <span className="font-mono">{formatNumber(row.win_rate)}%</span>
            <span className={`font-mono ${pnlColor(row.realized_pnl)}`}>{formatNumber(row.realized_pnl)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BlockReasonBlock({ rows }: { rows: BlockReasonStat[] }) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
      <div className="border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
        Block reasons
      </div>
      <div className="grid">
        {(rows.length ? rows.slice(0, 8) : [{ reason: "No block data", count: 0, symbols: [], last_seen: "" }]).map((row) => (
          <div key={row.reason} className="grid gap-2 border-b border-[var(--line)] px-3 py-2 text-xs last:border-0 md:grid-cols-[1fr_70px_140px]">
            <span className="leading-5">{row.reason}</span>
            <span className="font-mono text-[var(--muted)]">{row.count}</span>
            <span className="truncate text-[var(--muted)]">{row.symbols.join(", ") || "-"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
