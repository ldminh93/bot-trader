"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  Broadcast,
  CaretDown,
  Play,
  Stop,
  Warning,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { FlowChart, PositioningChart, PriceChart, ProfitChart } from "@/components/dashboard/market-charts";
import { TradeTable } from "@/components/dashboard/trade-table";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { useDashboard } from "@/hooks/use-dashboard";
import { api } from "@/lib/api";
import type { BotConfig, TrendState } from "@/lib/types";
import { formatCompact, formatNumber, pnlColor } from "@/lib/utils";

const SIGNAL_TIMEFRAMES = ["1m", "5m", "15m"];
const LEVERAGE_OPTIONS = [1, 3, 5, 10, 20];

function TrendBadge({ value }: { value: string }) {
  const styles = value === "LONG"
    ? "text-[var(--positive)] bg-[var(--positive)]/10"
    : value === "SHORT"
      ? "text-[var(--negative)] bg-[var(--negative)]/10"
      : "text-[var(--warning)] bg-[var(--warning)]/10";
  return <span className={`rounded-md px-2 py-1 text-[10px] font-bold ${styles}`}>{value}</span>;
}

function TrendStateBadge({ value = "SIDEWAY" }: { value?: TrendState }) {
  const styles: Record<TrendState, string> = {
    SIDEWAY: "bg-[#747d88]/15 text-[#aeb5bd]",
    EARLY_UPTREND: "bg-[#68d9a0]/12 text-[#79d9a7]",
    CONFIRMED_UPTREND: "bg-[var(--positive)]/15 text-[var(--positive)]",
    WEAK_UPTREND: "bg-[#e0c75b]/15 text-[#e0c75b]",
    EARLY_DOWNTREND: "bg-[#ff8e8e]/12 text-[#ff9898]",
    CONFIRMED_DOWNTREND: "bg-[var(--negative)]/15 text-[var(--negative)]",
    WEAK_DOWNTREND: "bg-[#e99a52]/15 text-[#e99a52]",
  };
  return (
    <span className={`rounded-md px-2 py-1 text-[10px] font-bold ${styles[value]}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0 px-4 py-3">
      <p className="truncate text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">{label}</p>
      <p className={`mt-1 truncate font-mono text-sm font-semibold ${tone ?? ""}`}>{value}</p>
      {detail && <p className="mt-0.5 truncate text-[10px] text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

export function DashboardConsole() {
  const [symbol, setSymbol] = useState<string | null>(null);
  const [scannerConfigs, setScannerConfigs] = useState<BotConfig[]>([]);
  const [busy, setBusy] = useState(false);
  const { config, setConfig, snapshot, trades, stats, logs, loading, error, refresh } = useDashboard(symbol);
  const openPosition = trades.find((trade) => trade.status === "OPEN");
  const liveModeEnabled = Boolean(config?.live_mode_requested && config.live_trading_available);
  const modeLabel = liveModeEnabled
    ? "LIVE"
    : config?.live_trading_available
      ? "PAPER · LIVE READY"
      : "PAPER · LIVE LOCKED";

  const refreshScannerConfigs = useCallback(async () => {
    const items = await api.configs();
    setScannerConfigs(items);
    setSymbol((current) => {
      if (current && items.some((item) => item.symbol === current)) return current;
      return items.find((item) => item.is_running)?.symbol ?? items[0]?.symbol ?? null;
    });
  }, []);

  useEffect(() => {
    void refreshScannerConfigs();
    window.addEventListener("focus", refreshScannerConfigs);
    return () => window.removeEventListener("focus", refreshScannerConfigs);
  }, [refreshScannerConfigs]);

  async function toggleBot() {
    if (!config || !symbol) return;
    setBusy(true);
    try {
      setConfig(config.is_running ? await api.stop(symbol) : await api.start(symbol));
    } finally {
      setBusy(false);
    }
  }

  async function changeSignalTimeframe(timeframe: string) {
    if (!config || !symbol || timeframe === config.timeframe_signal) return;
    setBusy(true);
    try {
      setConfig(await api.saveConfig({ symbol, timeframe_signal: timeframe }));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function changeLeverage(leverage: number) {
    if (!config || !symbol || leverage === config.leverage) return;
    setBusy(true);
    try {
      setConfig(await api.saveConfig({ symbol, leverage }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-[var(--line)] bg-[var(--background)]/95 px-4 backdrop-blur md:px-6">
        <div className="flex items-center gap-3">
          <div className="relative">
            <select
              aria-label="Trading symbol"
              value={symbol ?? ""}
              disabled={!scannerConfigs.length}
              onChange={(event) => setSymbol(event.target.value)}
              className="h-9 appearance-none rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--surface)] pl-3 pr-9 font-mono text-sm font-bold outline-none focus:border-[var(--accent)] disabled:opacity-50"
            >
              {!scannerConfigs.length && <option value="">No scanner coins</option>}
              {scannerConfigs.map((item) => (
                <option key={item.id} value={item.symbol}>
                  {item.symbol}{item.is_running ? " · scanning" : ""}
                </option>
              ))}
            </select>
            <CaretDown className="pointer-events-none absolute right-3 top-2.5 text-[var(--muted)]" size={15} />
          </div>
          <div className="relative">
            <select
              aria-label="Signal timeframe"
              value={config?.timeframe_signal ?? "15m"}
              disabled={!config || busy}
              onChange={(event) => void changeSignalTimeframe(event.target.value)}
              className="h-9 appearance-none rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--surface)] pl-3 pr-8 font-mono text-xs font-bold outline-none focus:border-[var(--accent)] disabled:opacity-50"
            >
              {SIGNAL_TIMEFRAMES.map((item) => <option key={item}>{item}</option>)}
            </select>
            <CaretDown className="pointer-events-none absolute right-2.5 top-2.5 text-[var(--muted)]" size={14} />
          </div>
          <div className="relative">
            <select
              aria-label="Trade leverage"
              value={config?.leverage ?? 10}
              disabled={!config || busy || Boolean(openPosition)}
              onChange={(event) => void changeLeverage(Number(event.target.value))}
              className="h-9 appearance-none rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--surface)] pl-3 pr-8 font-mono text-xs font-bold outline-none focus:border-[var(--accent)] disabled:opacity-50"
              title={openPosition ? "Close the current position before changing leverage" : "Trade leverage"}
            >
              {LEVERAGE_OPTIONS.map((item) => <option key={item} value={item}>x{item}</option>)}
            </select>
            <CaretDown className="pointer-events-none absolute right-2.5 top-2.5 text-[var(--muted)]" size={14} />
          </div>
          <div className="hidden items-baseline gap-2 sm:flex">
            <span className="font-mono text-lg font-bold">{snapshot ? formatNumber(snapshot.price, Number(snapshot.price) < 1 ? 6 : 2) : "-"}</span>
            <span className={pnlColor(snapshot?.open_interest_change_percent ?? 0)}>
              {snapshot ? `${formatNumber(snapshot.open_interest_change_percent)}% OI` : "Waiting for data"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden rounded-[var(--radius)] border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-2.5 py-1.5 text-xs font-bold text-[var(--accent)] sm:inline-flex">
            {modeLabel}
          </span>
          <Button
            variant={config?.is_running ? "danger" : "primary"}
            onClick={toggleBot}
            disabled={!config || busy}
          >
            {config?.is_running ? <Stop size={16} weight="fill" /> : <Play size={16} weight="fill" />}
            {config?.is_running ? "Stop bot" : "Start bot"}
          </Button>
        </div>
      </header>

      <div className="p-4 md:p-6">
        {error && (
          <div className="mb-4 flex items-start gap-3 rounded-[var(--radius)] border border-[var(--negative)]/40 bg-[var(--negative)]/10 p-3 text-sm text-[#ff9b9b]">
            <Warning className="mt-0.5 shrink-0" size={18} />
            {error}
          </div>
        )}
        {loading ? (
          <DashboardSkeleton />
        ) : (
          <div className="grid gap-4">
            <section className="grid overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] grid-cols-2 md:grid-cols-4 xl:grid-cols-9">
              <Metric label={`${config?.timeframe_signal ?? "Signal"} state`} value={snapshot?.trend.replaceAll("_", " ") ?? "-"} />
              <Metric label={`${config?.timeframe_trend ?? "1h"} state`} value={snapshot?.payload.trend_1h.replaceAll("_", " ") ?? "-"} />
              <Metric label="Risk multiplier" value={`${formatNumber((snapshot?.payload.risk_multiplier ?? 0) * 100, 0)}%`} />
              <Metric label="MA7" value={snapshot ? formatNumber(snapshot.ma7, 4) : "-"} />
              <Metric label="MA25" value={snapshot ? formatNumber(snapshot.ma25, 4) : "-"} />
              <Metric label="MA99" value={snapshot ? formatNumber(snapshot.ma99, 4) : "-"} />
              <Metric label="ADX 14" value={snapshot ? formatNumber(snapshot.adx) : "-"} detail={`Min ${config?.adx_min ?? 20}`} />
              <Metric label="ATR 14" value={snapshot ? formatNumber(snapshot.atr, 4) : "-"} />
              <Metric
                label="Funding"
                value={snapshot ? `${formatNumber(Number(snapshot.funding_rate) * 100, 4)}%` : "-"}
                tone={pnlColor(Number(snapshot?.funding_rate ?? 0) * -1)}
              />
            </section>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.75fr)]">
              <Panel className="min-w-0">
                <PanelHeader title="Price and moving averages" action={<span className="text-[10px] text-[var(--muted)]">{config?.timeframe_signal ?? snapshot?.timeframe ?? "-"} / last 60 bars</span>} />
                <div className="h-[310px] p-2">
                  {snapshot?.payload.candles?.length ? (
                    <PriceChart candles={snapshot.payload.candles} position={openPosition} />
                  ) : (
                    <EmptyChart />
                  )}
                </div>
              </Panel>

              <Panel>
                <PanelHeader
                  title="Signal engine"
                  action={snapshot ? (
                    <div className="flex items-center gap-2">
                      <TrendStateBadge value={snapshot.payload.trend_state} />
                      <TrendBadge value={snapshot.payload.signal} />
                    </div>
                  ) : undefined}
                />
                <div className="p-4">
                  <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius)] bg-[var(--line)]">
                    <div className="bg-[var(--background)] p-4">
                      <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Long score</p>
                      <p className="mt-1 font-mono text-3xl font-bold text-[var(--positive)]">{snapshot?.payload.long_score ?? 0}</p>
                    </div>
                    <div className="bg-[var(--background)] p-4">
                      <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Short score</p>
                      <p className="mt-1 font-mono text-3xl font-bold text-[var(--negative)]">{snapshot?.payload.short_score ?? 0}</p>
                    </div>
                  </div>
                  <div className="mt-4">
                    <p className="text-xs font-semibold">Decision factors</p>
                    <ul className="mt-2 grid gap-2">
                      {(snapshot?.payload.reasons ?? ["Waiting for the first bot cycle"]).map((reason) => (
                        <li key={reason} className="flex items-start gap-2 text-xs leading-5 text-[var(--muted)]">
                          <span className="mt-2 size-1 shrink-0 rounded-full bg-[var(--accent)]" />
                          {reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </Panel>
            </div>

            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-[1fr_1fr_0.9fr]">
              <Panel>
                <PanelHeader title="Order flow" />
                <div className="grid grid-cols-2 border-b border-[var(--line)]">
                  <Metric label="Delta" value={snapshot ? formatCompact(snapshot.delta) : "-"} tone={pnlColor(snapshot?.delta ?? 0)} />
                  <Metric label="CVD" value={snapshot ? formatCompact(snapshot.cvd) : "-"} tone={pnlColor(snapshot?.cvd ?? 0)} />
                </div>
                <div className="h-48 p-2">
                  {snapshot?.payload.candles?.length ? <FlowChart candles={snapshot.payload.candles} /> : <EmptyChart />}
                </div>
              </Panel>

              <Panel>
                <PanelHeader title="Positioning and participation" />
                <div className="grid grid-cols-2">
                  <Metric label="Open interest" value={snapshot ? formatCompact(snapshot.open_interest) : "-"} detail={`${formatNumber(snapshot?.open_interest_change_percent ?? 0)}% change`} tone={pnlColor(snapshot?.open_interest_change_percent ?? 0)} />
                  <Metric label="Volume" value={snapshot ? formatCompact(snapshot.volume) : "-"} detail={`MA20 ${formatCompact(snapshot?.volume_ma20 ?? 0)}`} />
                  <Metric label="Top accounts L/S" value={snapshot ? formatNumber(snapshot.top_trader_account_ratio, 3) : "-"} />
                  <Metric label="Top positions L/S" value={snapshot ? formatNumber(snapshot.top_trader_position_ratio, 3) : "-"} />
                </div>
                <div className="h-40 border-t border-[var(--line)] p-2">
                  {snapshot?.payload.market_history?.length ? (
                    <PositioningChart history={snapshot.payload.market_history} />
                  ) : (
                    <EmptyChart label="Open-interest and funding history will accumulate here." />
                  )}
                </div>
              </Panel>

              <Panel className="lg:col-span-2 xl:col-span-1">
                <PanelHeader
                  title="Open position"
                  action={openPosition ? (
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-[var(--accent)]/10 px-2 py-1 font-mono text-[10px] font-bold text-[var(--accent)]">
                        x{openPosition.leverage}
                      </span>
                      <TrendBadge value={openPosition.side} />
                    </div>
                  ) : undefined}
                />
                {openPosition ? (
                  <div className="grid grid-cols-2">
                    <Metric label="Entry" value={formatNumber(openPosition.entry_price, 4)} />
                    <Metric label="Quantity" value={formatNumber(openPosition.remaining_quantity, 5)} />
                    <Metric label="Leverage" value={`x${openPosition.leverage}`} detail={config?.margin_type.toUpperCase()} />
                    <Metric
                      label="Estimated margin"
                      value={`${formatNumber(
                        Number(openPosition.entry_price)
                          * Number(openPosition.remaining_quantity)
                          / openPosition.leverage,
                      )} USDT`}
                      detail={`Notional ${formatNumber(
                        Number(openPosition.entry_price) * Number(openPosition.remaining_quantity),
                      )} USDT`}
                    />
                    <Metric label="Stop loss" value={formatNumber(openPosition.stop_loss, 4)} />
                    <Metric label="TP1 / TP2" value={`${formatNumber(openPosition.take_profit_1, 3)} / ${formatNumber(openPosition.take_profit_2, 3)}`} />
                    <Metric label="Unrealized PnL" value={`${formatNumber(openPosition.unrealized_pnl)} USDT`} tone={pnlColor(openPosition.unrealized_pnl)} />
                    <Metric
                      label="Margin ROI"
                      value={`${formatNumber(openPosition.pnl_percent)}%`}
                      detail="Net PnL after fees"
                      tone={pnlColor(openPosition.pnl_percent)}
                    />
                  </div>
                ) : (
                  <div className="grid min-h-48 place-items-center px-6 text-center">
                    <div>
                      <p className="font-semibold">No open position</p>
                      <p className="mt-1 text-xs leading-5 text-[var(--muted)]">The bot will wait until score, trend, risk, and entry-location rules align.</p>
                    </div>
                  </div>
                )}
              </Panel>
            </div>

            <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
              <Panel>
                <PanelHeader title="Performance" />
                <div className="grid grid-cols-2 border-b border-[var(--line)] sm:grid-cols-4">
                  <Metric label="Total profit" value={`${formatNumber(stats.total_profit)} USDT`} tone={pnlColor(stats.total_profit)} />
                  <Metric label="Realized" value={formatNumber(stats.realized_pnl)} tone={pnlColor(stats.realized_pnl)} />
                  <Metric label="Win rate" value={`${formatNumber(stats.win_rate)}%`} />
                  <Metric label="Trades" value={String(stats.trades)} />
                </div>
                <div className="h-52 p-2">{stats.daily.length ? <ProfitChart stats={stats} /> : <EmptyChart />}</div>
              </Panel>

              <Panel>
                <PanelHeader title="Bot event stream" action={<Broadcast size={16} className={config?.is_running ? "text-[var(--positive)]" : "text-[var(--muted)]"} />} />
                <div className="h-[284px] overflow-y-auto p-2 scrollbar-thin">
                  {logs.length ? logs.slice(0, 30).map((log) => (
                    <div key={log.id} className="grid grid-cols-[68px_1fr] gap-3 rounded-md px-2 py-2 text-xs hover:bg-[var(--surface-raised)]">
                      <span className={`font-mono text-[10px] ${log.level === "ERROR" ? "text-[var(--negative)]" : log.level === "WARNING" ? "text-[var(--warning)]" : "text-[var(--muted)]"}`}>
                        {new Date(log.created_at).toLocaleTimeString()}
                      </span>
                      <p className="leading-5">{log.message}</p>
                    </div>
                  )) : <EmptyChart label="Bot events will appear here." />}
                </div>
              </Panel>
            </div>

            <Panel>
              <PanelHeader title="Recent trades" />
              <TradeTable trades={trades} limit={8} />
            </Panel>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function EmptyChart({ label = "No market series yet. Start the bot to collect data." }: { label?: string }) {
  return <div className="grid h-full place-items-center text-center text-xs text-[var(--muted)]">{label}</div>;
}

function DashboardSkeleton() {
  return (
    <div className="grid gap-4">
      <div className="h-20 animate-pulse rounded-[var(--radius)] bg-[var(--surface)]" />
      <div className="grid gap-4 xl:grid-cols-[1.65fr_0.75fr]">
        <div className="h-[365px] animate-pulse rounded-[var(--radius)] bg-[var(--surface)]" />
        <div className="h-[365px] animate-pulse rounded-[var(--radius)] bg-[var(--surface)]" />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((item) => <div key={item} className="h-64 animate-pulse rounded-[var(--radius)] bg-[var(--surface)]" />)}
      </div>
    </div>
  );
}
