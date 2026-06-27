"use client";

import { useEffect, useState } from "react";

import { DailyPnlChart, PriceChart, ProfitChart } from "@/components/dashboard/market-charts";
import { TradeTable } from "@/components/dashboard/trade-table";
import { PageFrame } from "@/components/page-frame";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { Trade, TradeStats } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

export function TradesConsole() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [selectedTradeId, setSelectedTradeId] = useState<number | null>(null);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    Promise.all([api.trades(), api.stats()]).then(([nextTrades, nextStats]) => {
      setTrades(nextTrades);
      setStats(nextStats);
      setSelectedTradeId(nextTrades[0]?.id ?? null);
    });
  }, []);

  const selectedTrade = trades.find((trade) => trade.id === selectedTradeId) ?? trades[0] ?? null;

  return (
    <PageFrame title="Trades" description="Execution history and realized strategy performance.">
      <div className="grid gap-4">
        <section className="grid overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] grid-cols-2 lg:grid-cols-4">
          <Stat label="Total PnL" value={`${formatNumber(stats?.total_profit ?? 0)} USDT`} tone={pnlColor(stats?.total_profit ?? 0)} />
          <Stat label="Win rate" value={`${formatNumber(stats?.win_rate ?? 0)}%`} />
          <Stat label="Closed trades" value={String(stats?.trades ?? 0)} />
          <Stat label="Average return" value={`${formatNumber(stats?.average_pnl_percent ?? 0)}%`} tone={pnlColor(stats?.average_pnl_percent ?? 0)} />
        </section>
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelHeader title="Profit curve" />
            <div className="h-64 p-2">{stats?.daily.length ? <ProfitChart stats={stats} /> : <Empty />}</div>
          </Panel>
          <Panel>
            <PanelHeader title="Daily PnL" />
            <div className="h-64 p-2">{stats?.daily.length ? <DailyPnlChart stats={stats} /> : <Empty />}</div>
          </Panel>
        </div>
        <Panel>
          <PanelHeader title="All trades" />
          <TradeTable trades={trades} onSelect={(trade) => setSelectedTradeId(trade.id)} selectedTradeId={selectedTrade?.id ?? null} />
        </Panel>
        <Panel>
          <PanelHeader title="Trade replay" action={selectedTrade ? <span className="text-[10px] text-[var(--muted)]">Click any trade row to inspect its entry context</span> : undefined} />
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

