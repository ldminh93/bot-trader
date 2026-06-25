"use client";

import { useEffect, useState } from "react";

import { DailyPnlChart, ProfitChart } from "@/components/dashboard/market-charts";
import { TradeTable } from "@/components/dashboard/trade-table";
import { PageFrame } from "@/components/page-frame";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { Trade, TradeStats } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

export function TradesConsole() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    Promise.all([api.trades(), api.stats()]).then(([nextTrades, nextStats]) => {
      setTrades(nextTrades);
      setStats(nextStats);
    });
  }, []);

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
          <TradeTable trades={trades} />
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

