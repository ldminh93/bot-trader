"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { DailyPnlChart, PriceChart, ProfitChart } from "@/components/dashboard/market-charts";
import { TradeTable } from "@/components/dashboard/trade-table";
import { PageFrame } from "@/components/page-frame";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { Trade, TradeStats } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

const FILTER_KEYS = ["symbol", "side", "close_reason", "grade", "tag", "hour"] as const;
type FilterKey = (typeof FILTER_KEYS)[number];

const FILTER_LABELS: Record<FilterKey, string> = {
  symbol: "Symbol",
  side: "Side",
  close_reason: "Close reason",
  grade: "Grade",
  tag: "Setup tag",
  hour: "Entry hour (UTC)",
};

function todayLocalDate(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function readFilters(): Record<FilterKey, string> {
  const params = new URLSearchParams(window.location.search);
  const result = {} as Record<FilterKey, string>;
  for (const key of FILTER_KEYS) {
    result[key] = params.get(key) ?? "";
  }
  return result;
}

function matchesFilters(trade: Trade, filters: Record<FilterKey, string>): boolean {
  if (filters.symbol && trade.symbol !== filters.symbol) return false;
  if (filters.side && trade.side !== filters.side) return false;
  if (filters.close_reason) {
    if (filters.close_reason === "No close reason") {
      if (trade.close_reason) return false;
    } else if (!trade.close_reason.startsWith(filters.close_reason)) {
      return false;
    }
  }
  if (filters.grade && !(trade.setup_tags || []).includes(`grade:${filters.grade}`)) return false;
  if (filters.tag && !(trade.setup_tags || []).includes(filters.tag)) return false;
  if (filters.hour) {
    const hour = trade.opened_at ? new Date(trade.opened_at).getUTCHours() : -1;
    if (String(hour).padStart(2, "0") !== filters.hour) return false;
  }
  return true;
}

function computeDailyPnl(trades: Trade[]): { day: string; pnl: number }[] {
  const byDay = new Map<string, number>();
  for (const trade of trades) {
    if (trade.status !== "CLOSED" || !trade.closed_at) continue;
    const day = trade.closed_at.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + Number(trade.realized_pnl));
  }
  return Array.from(byDay.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, pnl]) => ({ day, pnl }));
}

export function TradesConsole() {
  const router = useRouter();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [selectedTradeId, setSelectedTradeId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [date, setDate] = useState(todayLocalDate());
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<Record<FilterKey, string>>({
    symbol: "",
    side: "",
    close_reason: "",
    grade: "",
    tag: "",
    hour: "",
  });

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    setFilters(readFilters());
    api.stats().then(setStats);
  }, []);

  useEffect(() => {
    setLoading(true);
    api.trades(undefined, date || undefined).then((nextTrades) => {
      setTrades(nextTrades);
      setSelectedTradeId(nextTrades[0]?.id ?? null);
      setLoading(false);
    });
  }, [date]);

  const activeFilters = FILTER_KEYS.filter((key) => filters[key]);
  const isDateScoped = date !== "";

  const filteredTrades = useMemo(
    () => (activeFilters.length ? trades.filter((trade) => matchesFilters(trade, filters)) : trades),
    [trades, filters, activeFilters.length]
  );

  const filteredStats = useMemo(() => {
    if (!stats) return stats;
    if (!activeFilters.length && !isDateScoped) return stats;
    const closed = filteredTrades.filter((trade) => trade.status === "CLOSED");
    const wins = closed.filter((trade) => Number(trade.realized_pnl) > 0).length;
    const totalPnl = closed.reduce((sum, trade) => sum + Number(trade.realized_pnl), 0);
    const avgPct = closed.length
      ? closed.reduce((sum, trade) => sum + Number(trade.pnl_percent), 0) / closed.length
      : 0;
    return {
      ...stats,
      total_profit: totalPnl,
      trades: closed.length,
      win_rate: closed.length ? (wins / closed.length) * 100 : 0,
      average_pnl_percent: avgPct,
      daily: computeDailyPnl(filteredTrades),
    };
  }, [stats, filteredTrades, activeFilters.length, isDateScoped]);

  function clearFilters() {
    router.push("/trades");
    setFilters({ symbol: "", side: "", close_reason: "", grade: "", tag: "", hour: "" });
  }

  const selectedTrade = filteredTrades.find((trade) => trade.id === selectedTradeId) ?? filteredTrades[0] ?? null;

  async function exportReplay() {
    if (!selectedTrade) return;
    const result = await api.exportReplay(selectedTrade.id);
    setMessage(result.message);
  }

  return (
    <PageFrame title="Trades" description="Execution history and realized strategy performance.">
      <div className="grid gap-4">
        {message && (
          <div className="rounded-[var(--radius)] border border-[var(--positive)]/40 bg-[var(--positive)]/10 p-3 text-sm text-[#8ce9b8]">
            {message}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] p-3 text-xs">
          <span className="font-semibold text-[var(--text)]">Date:</span>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--background)] px-2 py-1 text-xs font-mono text-[var(--text)] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setDate(todayLocalDate())}
            className="rounded-full border border-[var(--line)] px-2 py-1 font-semibold text-[var(--muted)] hover:text-[var(--text)]"
          >
            Today
          </button>
          {isDateScoped && (
            <button
              type="button"
              onClick={() => setDate("")}
              className="ml-auto font-semibold text-[var(--accent)] hover:underline"
            >
              Show all time
            </button>
          )}
          {loading && <span className="text-[var(--muted)]">Loading…</span>}
        </div>
        {activeFilters.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius)] border border-[var(--accent)]/40 bg-[var(--accent)]/10 p-3 text-xs">
            <span className="font-semibold text-[var(--text)]">Filtered by:</span>
            {activeFilters.map((key) => (
              <span key={key} className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-2 py-1 font-mono">
                {FILTER_LABELS[key]}: {filters[key]}
              </span>
            ))}
            <button
              type="button"
              onClick={clearFilters}
              className="ml-auto font-semibold text-[var(--accent)] hover:underline"
            >
              Clear filter
            </button>
          </div>
        )}
        <section className="grid overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] grid-cols-2 lg:grid-cols-4">
          <Stat label="Total PnL" value={`${formatNumber(filteredStats?.total_profit ?? 0)} USDT`} tone={pnlColor(filteredStats?.total_profit ?? 0)} />
          <Stat label="Win rate" value={`${formatNumber(filteredStats?.win_rate ?? 0)}%`} />
          <Stat label="Closed trades" value={String(filteredStats?.trades ?? 0)} />
          <Stat label="Average return" value={`${formatNumber(filteredStats?.average_pnl_percent ?? 0)}%`} tone={pnlColor(filteredStats?.average_pnl_percent ?? 0)} />
        </section>
        <div className="grid min-w-0 gap-4 lg:grid-cols-2">
          <Panel className="min-w-0">
            <PanelHeader title="Profit curve" />
            <div className="h-64 p-2">{filteredStats?.daily.length ? <ProfitChart stats={filteredStats} /> : <Empty />}</div>
          </Panel>
          <Panel className="min-w-0">
            <PanelHeader title="Daily PnL" />
            <div className="h-64 p-2">{filteredStats?.daily.length ? <DailyPnlChart stats={filteredStats} /> : <Empty />}</div>
          </Panel>
        </div>
        <Panel className="min-w-0">
          <PanelHeader title="All trades" />
          <TradeTable trades={filteredTrades} onSelect={(trade) => setSelectedTradeId(trade.id)} selectedTradeId={selectedTrade?.id ?? null} />
        </Panel>
        <Panel className="min-w-0">
          <PanelHeader
            title="Trade replay"
            action={selectedTrade?.status === "CLOSED" ? (
              <button type="button" onClick={exportReplay} className="text-[10px] font-bold text-[var(--accent)]">
                Export Discord
              </button>
            ) : selectedTrade ? <span className="text-[10px] text-[var(--muted)]">Click any trade row to inspect its entry context</span> : undefined}
          />
          {selectedTrade ? (
            <div className="grid gap-4 p-4 xl:grid-cols-[1.35fr_0.65fr]">
              <div className="h-[320px]">
                {selectedTrade.replay_payload?.candles?.length ? (
                  <PriceChart candles={selectedTrade.replay_payload.candles} position={selectedTrade} />
                ) : (
                  <Empty />
                )}
              </div>
              <div className="grid gap-3 content-start">
                <ReplayStat label="Signal" value={selectedTrade.replay_payload?.signal ?? selectedTrade.side} />
                <ReplayStat label="Regime" value={selectedTrade.replay_payload?.regime_label ?? "-"} />
                <ReplayStat label="Confidence" value={String(selectedTrade.replay_payload?.confidence_score ?? 0)} />
                <ReplayStat label="Execution" value={`x${selectedTrade.replay_payload?.effective_leverage ?? selectedTrade.leverage} / ${formatNumber(selectedTrade.replay_payload?.tp_r_multiple ?? 0, 2)}R`} />
                <ReplayStat label="Bias" value={selectedTrade.replay_payload?.higher_timeframe_bias?.alignment ?? "-"} />
                <div className="rounded-[var(--radius)] border border-[var(--line)] p-3 text-xs">
                  <p className="font-semibold">Entry reasons</p>
                  <ul className="mt-2 grid gap-2 text-[var(--muted)]">
                    {(selectedTrade.replay_payload?.reasons?.length ? selectedTrade.replay_payload.reasons : [selectedTrade.open_reason]).map((reason) => (
                      <li key={reason} className="leading-5">{reason}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-[var(--radius)] border border-[var(--line)] p-3 text-xs">
                  <p className="font-semibold">Higher timeframe / regime notes</p>
                  <ul className="mt-2 grid gap-2 text-[var(--muted)]">
                    {[
                      ...(selectedTrade.replay_payload?.higher_timeframe_bias?.reasons ?? []),
                      ...(selectedTrade.replay_payload?.regime_notes ?? []),
                    ].slice(0, 8).map((reason) => (
                      <li key={reason} className="leading-5">{reason}</li>
                    ))}
                  </ul>
                </div>
                {selectedTrade.status === "CLOSED" ? (
                  <div className="rounded-[var(--radius)] border border-[var(--line)] p-3 text-xs">
                    <p className="font-semibold">Close reason</p>
                    <p className="mt-2 leading-5 text-[var(--muted)]">{selectedTrade.close_reason || "-"}</p>
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="p-4"><Empty /></div>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className="p-4"><p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">{label}</p><p className={`mt-1 font-mono text-lg font-bold ${tone ?? ""}`}>{value}</p></div>;
}

function Empty() {
  return <div className="grid h-full place-items-center text-xs text-[var(--muted)]">Closed trades will populate this chart.</div>;
}

function ReplayStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)] p-3">
      <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">{label}</p>
      <p className="mt-1 font-mono text-sm font-bold">{value}</p>
    </div>
  );
}

