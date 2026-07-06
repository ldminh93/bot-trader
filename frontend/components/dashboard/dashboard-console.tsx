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
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { FlowChart, PnlAttributionChart, PositioningChart, PriceChart, ProfitChart, WinRateSparkline } from "@/components/dashboard/market-charts";
import { TradeTable } from "@/components/dashboard/trade-table";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { useDashboard } from "@/hooks/use-dashboard";
import { api } from "@/lib/api";
import type { AnalyticsBucket, BacktestResult, BotConfig, LiveSyncHealth, OpportunityItem, SymbolAnalyticsBucket, TrendState } from "@/lib/types";
import { formatCompact, formatNumber, pnlColor } from "@/lib/utils";

const SIGNAL_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h"];
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
    <div className="min-w-0 px-3 py-3 sm:px-4">
      <p className="text-[9px] font-semibold uppercase tracking-[0.1em] leading-[1.35] text-[var(--muted)] sm:text-[10px]">{label}</p>
      <p className={`mt-1 break-words font-mono text-[15px] font-semibold leading-tight sm:text-sm ${tone ?? ""}`}>{value}</p>
      {detail && <p className="mt-1 text-[10px] leading-4 text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

export function DashboardConsole() {
  const [symbol, setSymbol] = useState<string | null>(null);
  const [scannerConfigs, setScannerConfigs] = useState<BotConfig[]>([]);
  const [busy, setBusy] = useState(false);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [liveSync, setLiveSync] = useState<LiveSyncHealth | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [binanceBalance, setBinanceBalance] = useState<number | null>(null);
  const { config, setConfig, setSnapshot, snapshot, trades, stats, logs, loading, error, refresh } = useDashboard(symbol);
  const [nextCycle, setNextCycle] = useState(5);
  const cycleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setNextCycle(5);
    if (cycleTimerRef.current) clearInterval(cycleTimerRef.current);
    cycleTimerRef.current = setInterval(() => setNextCycle((n) => Math.max(0, n - 1)), 1000);
    return () => { if (cycleTimerRef.current) clearInterval(cycleTimerRef.current); };
  }, [snapshot?.id]);

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

  const refreshLiveSync = useCallback(async () => {
    try {
      setLiveSync(await api.liveSync());
    } catch {
      setLiveSync(null);
    }
  }, []);

  useEffect(() => {
    void refreshLiveSync();
    const timer = window.setInterval(refreshLiveSync, 20_000);
    return () => window.clearInterval(timer);
  }, [refreshLiveSync]);

  const refreshOpportunities = useCallback(async () => {
    try {
      setOpportunities(await api.opportunities());
    } catch {
      setOpportunities([]);
    }
  }, []);

  useEffect(() => {
    void refreshOpportunities();
    const timer = window.setInterval(refreshOpportunities, 20_000);
    return () => window.clearInterval(timer);
  }, [refreshOpportunities]);

  const refreshBinanceBalance = useCallback(async () => {
    try {
      const result = await api.binanceBalance();
      setBinanceBalance(result.balance);
    } catch {
      setBinanceBalance(null);
    }
  }, []);

  useEffect(() => {
    void refreshBinanceBalance();
    const timer = window.setInterval(refreshBinanceBalance, 30_000);
    return () => window.clearInterval(timer);
  }, [refreshBinanceBalance]);

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
    setSnapshot(null);
    setConfig({ ...config, timeframe_signal: timeframe });
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

  async function closePosition() {
    if (!symbol || !openPosition) return;
    setBusy(true);
    try {
      await api.closePosition(symbol);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function runBacktest() {
    if (!symbol) return;
    setBusy(true);
    try {
      setBacktest(await api.backtest(symbol));
    } finally {
      setBusy(false);
    }
  }

  async function runKillSwitch() {
    const confirmed = window.confirm("Stop all bots and close every open position?");
    if (!confirmed) return;
    setBusy(true);
    try {
      await api.killSwitch();
      await Promise.all([refresh(), refreshScannerConfigs(), refreshLiveSync()]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <header className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)]/95 px-4 backdrop-blur md:px-6">
        <div className="flex flex-col gap-3 py-3 md:flex-row md:items-center md:justify-between">
          <div className="grid min-w-0 gap-3">
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_84px_84px] gap-2 sm:grid-cols-[minmax(0,1fr)_96px_96px]">
              <div className="relative min-w-0">
                <select
                  aria-label="Trading symbol"
                  value={symbol ?? ""}
                  disabled={!scannerConfigs.length}
                  onChange={(event) => setSymbol(event.target.value)}
                  className="h-10 w-full appearance-none rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--surface)] pl-3 pr-9 font-mono text-sm font-bold outline-none focus:border-[var(--accent)] disabled:opacity-50"
                >
                  {!scannerConfigs.length && <option value="">No scanner coins</option>}
                  {scannerConfigs.map((item) => (
                    <option key={item.id} value={item.symbol}>
                      {item.symbol}{item.is_running ? " · scanning" : ""}
                    </option>
                  ))}
                </select>
                <CaretDown className="pointer-events-none absolute right-3 top-3 text-[var(--muted)]" size={15} />
              </div>
              <div className="relative">
                <select
                  aria-label="Signal timeframe"
                  value={config?.timeframe_signal ?? "15m"}
                  disabled={!config || busy}
                  onChange={(event) => void changeSignalTimeframe(event.target.value)}
                  className="h-10 w-full appearance-none rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--surface)] pl-3 pr-8 font-mono text-xs font-bold outline-none focus:border-[var(--accent)] disabled:opacity-50"
                >
                  {SIGNAL_TIMEFRAMES.map((item) => <option key={item}>{item}</option>)}
                </select>
                <CaretDown className="pointer-events-none absolute right-2.5 top-3 text-[var(--muted)]" size={14} />
              </div>
              <div className="relative">
                <select
                  aria-label="Trade leverage"
                  value={config?.leverage ?? 10}
                  disabled={!config || busy || Boolean(openPosition)}
                  onChange={(event) => void changeLeverage(Number(event.target.value))}
                  className="h-10 w-full appearance-none rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--surface)] pl-3 pr-8 font-mono text-xs font-bold outline-none focus:border-[var(--accent)] disabled:opacity-50"
                  title={openPosition ? "Close the current position before changing leverage" : "Trade leverage"}
                >
                  {LEVERAGE_OPTIONS.map((item) => <option key={item} value={item}>x{item}</option>)}
                </select>
                <CaretDown className="pointer-events-none absolute right-2.5 top-3 text-[var(--muted)]" size={14} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 md:hidden">
              <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
                <p className="text-[9px] uppercase tracking-[0.1em] text-[var(--muted)]">Price</p>
                <p className="mt-1 font-mono text-sm font-bold">
                  {snapshot ? formatNumber(snapshot.price, Number(snapshot.price) < 1 ? 6 : 2) : "-"}
                </p>
              </div>
              <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
                <p className="text-[9px] uppercase tracking-[0.1em] text-[var(--muted)]">OI change</p>
                <p className={`mt-1 font-mono text-sm font-bold ${pnlColor(snapshot?.open_interest_change_percent ?? 0)}`}>
                  {snapshot ? `${formatNumber(snapshot.open_interest_change_percent)}%` : "-"}
                </p>
              </div>
            </div>
            <div className="hidden items-baseline gap-2 md:flex">
              <span className="font-mono text-lg font-bold">{snapshot ? formatNumber(snapshot.price, Number(snapshot.price) < 1 ? 6 : 2) : "-"}</span>
              <span className={pnlColor(snapshot?.open_interest_change_percent ?? 0)}>
                {snapshot ? `${formatNumber(snapshot.open_interest_change_percent)}% OI` : "Waiting for data"}
              </span>
            </div>
          </div>
          <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center md:justify-end">
            {config?.is_running && (
              <span className="inline-flex items-center gap-1.5 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] px-2.5 py-2 font-mono text-xs text-[var(--muted)]">
                <span className={`size-1.5 rounded-full ${nextCycle > 0 ? "bg-[var(--muted)]" : "animate-pulse bg-[var(--positive)]"}`} />
                {nextCycle > 0 ? `next cycle ${nextCycle}s` : "scanning…"}
              </span>
            )}
            <span className="inline-flex rounded-[var(--radius)] border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-2.5 py-2 text-xs font-bold text-[var(--accent)]">
              {modeLabel}
            </span>
            <Button
              variant={config?.is_running ? "danger" : "primary"}
              onClick={toggleBot}
              disabled={!config || busy}
              className="h-10 w-full sm:w-auto"
            >
              {config?.is_running ? <Stop size={16} weight="fill" /> : <Play size={16} weight="fill" />}
              {config?.is_running ? "Stop bot" : "Start bot"}
            </Button>
          </div>
        </div>
      </header>

      <div className="overflow-x-auto p-4 md:p-6">
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
            <section className="grid grid-cols-3 overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-9">
              <Metric label={`${config?.timeframe_signal ?? "Signal"} state`} value={snapshot?.trend.replaceAll("_", " ") ?? "-"} />
              <Metric label={`${config?.timeframe_trend ?? "1h"} state`} value={snapshot?.payload.trend_1h.replaceAll("_", " ") ?? "-"} />
              <Metric label="Risk multiplier" value={`${formatNumber((snapshot?.payload.risk_multiplier ?? 0) * 100, 0)}%`} />
              <Metric label="MA7" value={snapshot ? formatNumber(snapshot.ma7, 4) : "-"} />
              <Metric label="MA25" value={snapshot ? formatNumber(snapshot.ma25, 4) : "-"} />
              <Metric label="MA99" value={snapshot ? formatNumber(snapshot.ma99, 4) : "-"} />
              <Metric label={`ADX ${config?.adx_period ?? 14}`} value={snapshot ? formatNumber(snapshot.adx) : "-"} detail={`Min ${config?.adx_min ?? 20}`} />
              <Metric label={`ATR ${config?.adx_period ?? 14}`} value={snapshot ? formatNumber(snapshot.atr, 4) : "-"} />
              <Metric
                label="Funding"
                value={snapshot ? `${formatNumber(Number(snapshot.funding_rate) * 100, 4)}%` : "-"}
                tone={pnlColor(Number(snapshot?.funding_rate ?? 0) * -1)}
              />
            </section>

            <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.75fr)]">
              <Panel className="min-w-0">
                <PanelHeader title="Price and moving averages" action={<span className="text-[10px] text-[var(--muted)] sm:text-right">{config?.timeframe_signal ?? snapshot?.timeframe ?? "-"} / draggable history</span>} />
                <div className="h-[295px] w-full overflow-hidden sm:h-[345px]">
                  {snapshot?.payload.candles?.length ? (
                    <PriceChart candles={snapshot.payload.candles} position={openPosition} />
                  ) : (
                    <EmptyChart />
                  )}
                </div>
              </Panel>

              <Panel className="min-w-0">
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
                    <div className="bg-[var(--background)] p-3 sm:p-4">
                      <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Long score</p>
                      <p className="mt-1 font-mono text-2xl font-bold text-[var(--positive)] sm:text-3xl">{snapshot?.payload.long_score ?? 0}</p>
                    </div>
                    <div className="bg-[var(--background)] p-3 sm:p-4">
                      <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Short score</p>
                      <p className="mt-1 font-mono text-2xl font-bold text-[var(--negative)] sm:text-3xl">{snapshot?.payload.short_score ?? 0}</p>
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

            <Panel className="min-w-0">
              <PanelHeader
                title="Higher-timeframe bias"
                action={snapshot?.payload.higher_timeframe_bias ? (
                  <span className={`rounded-md px-2 py-1 text-[10px] font-bold ${snapshot.payload.higher_timeframe_bias.alignment === "aligned" ? "bg-[var(--positive)]/15 text-[var(--positive)]" : "bg-[var(--warning)]/15 text-[var(--warning)]"}`}>
                    {snapshot.payload.higher_timeframe_bias.alignment}
                  </span>
                ) : undefined}
              />
              <div className="grid grid-cols-2 gap-4 p-4 md:grid-cols-4">
                <Metric label="Signal trend" value={snapshot?.payload.higher_timeframe_bias?.signal_state.replaceAll("_", " ") ?? "-"} />
                <Metric label={`${config?.timeframe_trend ?? "1h"} trend`} value={snapshot?.payload.higher_timeframe_bias?.higher_state.replaceAll("_", " ") ?? "-"} />
                <Metric label="Regime" value={snapshot?.payload.regime_label ?? "-"} detail={(snapshot?.payload.regime ?? "").replaceAll("_", " ")} />
                <Metric
                  label="Execution profile"
                  value={`x${snapshot?.payload.effective_leverage ?? config?.leverage ?? 0} / ${formatNumber(snapshot?.payload.tp_r_multiple ?? 0, 2)}R`}
                  detail={`confidence ${snapshot?.payload.confidence_score ?? 0}`}
                />
              </div>
              <div className="grid gap-4 border-t border-[var(--line)] p-4 md:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold">Higher-timeframe reasons</p>
                  <ul className="mt-2 grid gap-2">
                    {(snapshot?.payload.higher_timeframe_bias?.reasons?.length ? snapshot.payload.higher_timeframe_bias.reasons : ["Waiting for current higher-timeframe analysis"]).map((reason) => (
                      <li key={reason} className="flex items-start gap-2 text-xs leading-5 text-[var(--muted)]">
                        <span className="mt-2 size-1 shrink-0 rounded-full bg-[var(--accent)]" />
                        {reason}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-semibold">Regime notes</p>
                  <ul className="mt-2 grid gap-2">
                    {(snapshot?.payload.regime_notes?.length ? snapshot.payload.regime_notes : ["Execution profile notes will appear here."]).map((reason) => (
                      <li key={reason} className="flex items-start gap-2 text-xs leading-5 text-[var(--muted)]">
                        <span className="mt-2 size-1 shrink-0 rounded-full bg-[var(--accent)]" />
                        {reason}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Panel>

            <div className="grid min-w-0 gap-4 lg:grid-cols-2 xl:grid-cols-[1fr_1fr_0.9fr]">
              <Panel className="min-w-0">
                <PanelHeader title="Order flow" />
                <div className="grid grid-cols-2 border-b border-[var(--line)]">
                  <Metric label="Delta" value={snapshot ? formatCompact(snapshot.delta) : "-"} tone={pnlColor(snapshot?.delta ?? 0)} />
                  <Metric label="CVD" value={snapshot ? formatCompact(snapshot.cvd) : "-"} tone={pnlColor(snapshot?.cvd ?? 0)} />
                </div>
                <div className="h-40 overflow-hidden p-2 sm:h-48">
                  {snapshot?.payload.candles?.length ? <FlowChart candles={snapshot.payload.candles} /> : <EmptyChart />}
                </div>
              </Panel>

              <Panel className="min-w-0">
                <PanelHeader title="Positioning and participation" />
                <div className="grid grid-cols-2">
                  <Metric label="Open interest" value={snapshot ? formatCompact(snapshot.open_interest) : "-"} detail={`${formatNumber(snapshot?.open_interest_change_percent ?? 0)}% change`} tone={pnlColor(snapshot?.open_interest_change_percent ?? 0)} />
                  <Metric label="Volume" value={snapshot ? formatCompact(snapshot.volume) : "-"} detail={`MA20 ${formatCompact(snapshot?.volume_ma20 ?? 0)}`} />
                  <Metric label="Top accounts L/S" value={snapshot ? formatNumber(snapshot.top_trader_account_ratio, 3) : "-"} />
                  <Metric label="Top positions L/S" value={snapshot ? formatNumber(snapshot.top_trader_position_ratio, 3) : "-"} />
                </div>
                <div className="h-36 overflow-hidden border-t border-[var(--line)] p-2 sm:h-40">
                  {snapshot?.payload.market_history?.length ? (
                    <PositioningChart history={snapshot.payload.market_history} />
                  ) : (
                    <EmptyChart label="Open-interest and funding history will accumulate here." />
                  )}
                </div>
              </Panel>

              <Panel className="min-w-0 lg:col-span-2 xl:col-span-1">
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
                  <div>
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
                    <div className="flex gap-2 border-t border-[var(--line)] p-4">
                      <Button variant="danger" disabled={busy} onClick={closePosition}>
                        <Stop size={16} weight="fill" />
                        Close position
                      </Button>
                    </div>
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

            <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_1fr]">
              <Panel className="min-w-0">
                <PanelHeader title="Performance" />
                <div className="grid grid-cols-2 border-b border-[var(--line)] sm:grid-cols-4">
                  <Metric label="Total profit" value={`${formatNumber(stats.total_profit)} USDT`} tone={pnlColor(stats.total_profit)} />
                  <Metric label="Realized" value={formatNumber(stats.realized_pnl)} tone={pnlColor(stats.realized_pnl)} />
                  <Metric label="Win rate" value={`${formatNumber(stats.win_rate)}%`} />
                  <Metric label="Trades" value={String(stats.trades)} />
                </div>
                <div className="grid grid-cols-3 border-b border-[var(--line)]">
                  <Metric
                    label={binanceBalance !== null ? "Balance (Binance)" : "Balance"}
                    value={`${formatNumber(binanceBalance ?? stats.current_balance ?? 0)} USDT`}
                    detail={binanceBalance !== null
                      ? `simulated ${formatNumber(stats.current_balance ?? 0)} USDT · peak ${formatNumber(stats.peak_balance ?? 0)} USDT`
                      : `peak ${formatNumber(stats.peak_balance ?? 0)} USDT`}
                  />
                  <Metric
                    label="Drawdown"
                    value={`${formatNumber(stats.drawdown_pct ?? 0)}%`}
                    tone={(stats.drawdown_pct ?? 0) > 10 ? "text-[var(--negative)]" : (stats.drawdown_pct ?? 0) > 5 ? "text-[var(--warning)]" : "text-[var(--muted)]"}
                  />
                  <Metric label="Avg trade" value={`${formatNumber(stats.average_pnl_percent ?? 0)}%`} detail="Margin ROI" />
                </div>
                <div className="grid sm:grid-cols-2">
                  <div className="h-44 overflow-hidden border-r border-[var(--line)] p-2 sm:h-48">
                    {stats.daily.length ? <ProfitChart stats={stats} /> : <EmptyChart />}
                  </div>
                  <div className="h-44 overflow-hidden p-2 sm:h-48">
                    <WinRateSparkline trades={trades} />
                  </div>
                </div>
              </Panel>

              <Panel className="min-w-0">
                <PanelHeader title="Bot event stream" action={<Broadcast size={16} className={config?.is_running ? "text-[var(--positive)]" : "text-[var(--muted)]"} />} />
                <div className="h-[240px] overflow-y-auto p-2 scrollbar-thin sm:h-[284px]">
                  {logs.length ? logs.slice(0, 30).map((log) => (
                    <div key={log.id} className="grid gap-1 rounded-md px-2 py-2 text-xs hover:bg-[var(--surface-raised)] sm:grid-cols-[132px_1fr] sm:gap-3">
                      <span className={`font-mono text-[10px] ${log.level === "ERROR" ? "text-[var(--negative)]" : log.level === "WARNING" ? "text-[var(--warning)]" : "text-[var(--muted)]"}`}>
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                      <p className="leading-5">{log.message}</p>
                    </div>
                  )) : <EmptyChart label="Bot events will appear here." />}
                </div>
              </Panel>
            </div>

            <Panel className="min-w-0">
              <PanelHeader
                title="Opportunity scoreboard"
                action={<span className="text-[10px] text-[var(--muted)]">Ranked by setup quality</span>}
              />
              <div className="grid gap-2 p-2">
                {(opportunities.length ? opportunities.slice(0, 10) : []).map((item) => (
                  <button
                    key={item.symbol}
                    type="button"
                    onClick={() => setSymbol(item.symbol)}
                    className={`rounded-md border border-[var(--line)] px-3 py-2 text-left text-xs hover:bg-[var(--surface-raised)] ${symbol === item.symbol ? "border-[var(--accent)] bg-[var(--accent)]/[0.05]" : ""}`}
                  >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                      <span className="font-mono font-bold">{item.symbol}</span>
                      <span className={`font-bold ${gradeTone(item.grade)}`}>Grade {item.grade}</span>
                      <span className={`font-bold ${item.signal === "LONG" ? "text-[var(--positive)]" : item.signal === "SHORT" ? "text-[var(--negative)]" : "text-[var(--muted)]"}`}>
                        {item.signal.replaceAll("_", " ")}
                      </span>
                      <span className="font-mono text-[var(--muted)]">{item.score}</span>
                      <span className="truncate text-[var(--muted)]">
                        {item.regime_label} / {item.alignment}{item.is_stale ? " · stale" : ""}
                      </span>
                    </div>
                  </button>
                ))}
                {!opportunities.length && <EmptyChart label="Opportunity rankings will appear after snapshots are collected." />}
              </div>
            </Panel>

            <Panel className="min-w-0">
              <PanelHeader
                title="Why not trade?"
                action={<span className="text-[10px] text-[var(--muted)]">Current blockers by scanner coin</span>}
              />
              <div className="grid gap-2 p-2">
                {opportunities.filter((item) => item.signal === "NO_TRADE").slice(0, 12).map((item) => (
                  <div key={item.symbol} className="rounded-md border border-[var(--line)] px-3 py-2 text-xs">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                      <span className="font-mono font-bold">{item.symbol}</span>
                      <span className={`font-bold ${gradeTone(item.grade)}`}>Grade {item.grade}</span>
                    </div>
                    <p className="mt-1 text-[var(--muted)]">{item.reasons[0] ?? "Waiting for a current snapshot"}</p>
                  </div>
                ))}
                {!opportunities.some((item) => item.signal === "NO_TRADE") && (
                  <EmptyChart label="No blocked scanner coins in the latest opportunity list." />
                )}
              </div>
            </Panel>

            <Panel className="min-w-0">
              <PanelHeader
                title="Live sync health"
                action={(
                  <Button type="button" size="sm" variant="danger" disabled={busy} onClick={runKillSwitch}>
                    <Stop size={15} weight="fill" />
                    Kill switch
                  </Button>
                )}
              />
              <div className="grid grid-cols-2 border-b border-[var(--line)] sm:grid-cols-4">
                <Metric label="Live checks" value={liveSync?.enabled ? "Enabled" : "Disabled"} />
                <Metric label="Credential" value={liveSync?.credential_ready ? "Ready" : "Not ready"} />
                <Metric label="Mismatches" value={String(liveSync?.mismatches ?? 0)} tone={(liveSync?.mismatches ?? 0) > 0 ? "text-[var(--negative)]" : "text-[var(--positive)]"} />
                <Metric label="Symbols checked" value={String(liveSync?.rows.length ?? 0)} />
              </div>
              <div className="max-h-72 overflow-y-auto p-2 scrollbar-thin">
                {(liveSync?.rows.length ? liveSync.rows : []).slice(0, 12).map((row) => (
                  <div key={row.symbol} className="grid gap-2 rounded-md px-2 py-2 text-xs hover:bg-[var(--surface-raised)] md:grid-cols-[90px_90px_90px_1fr]">
                    <span className="font-mono font-bold">{row.symbol}</span>
                    <span className={row.status === "mismatch" ? "font-bold text-[var(--negative)]" : row.status === "synced" ? "font-bold text-[var(--positive)]" : "text-[var(--muted)]"}>
                      {row.status.replaceAll("_", " ")}
                    </span>
                    <span className="font-mono text-[var(--muted)]">ex {formatNumber(row.exchange_quantity, 5)}</span>
                    <span className="text-[var(--muted)]">{row.detail}</span>
                  </div>
                ))}
                {!liveSync?.rows.length && <EmptyChart label="Live sync health will appear here." />}
              </div>
            </Panel>

            <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_1fr]">
              <Panel className="min-w-0">
                <PanelHeader
                  title="PnL attribution"
                  action={<span className="text-[10px] text-[var(--muted)]">Daily stacked by close reason</span>}
                />
                <div className="h-52 overflow-hidden p-2 sm:h-60">
                  <PnlAttributionChart trades={trades} />
                </div>
              </Panel>

              <Panel className="min-w-0">
                <PanelHeader
                  title="Analytics"
                  action={<span className="text-[10px] text-[var(--muted)]">Journal, setup tags, and timing breakdowns</span>}
                />
                <div className="grid gap-4 p-4 md:grid-cols-2">
                  <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
                    <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                      <span>By symbol</span>
                      <span className="normal-case font-normal">Sorted by total PnL — which tokens to keep, trim, or drop</span>
                    </div>
                    <SymbolDetailTable rows={stats.analytics.by_symbol} />
                  </div>
                  <AnalyticsBlock title="By side" rows={stats.analytics.by_side} filterKey="side" />
                  <AnalyticsBlock title="By close reason" rows={stats.analytics.by_close_reason} filterKey="close_reason" />
                  <AnalyticsBlock title="By grade" rows={stats.analytics.by_grade} filterKey="grade" />
                  <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
                    <div className="border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                      Best entry hour
                      <span className="ml-2 normal-case font-normal">UTC — hover cells for details</span>
                    </div>
                    <HourHeatmap rows={stats.analytics.by_hour} />
                  </div>
                  <div className="rounded-[var(--radius)] border border-[var(--line)] md:col-span-2">
                    <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                      <span>Setup tag P&L</span>
                      <span className="normal-case font-normal">Sorted by total PnL</span>
                    </div>
                    <TagPnlTable rows={stats.analytics.by_setup_tag} />
                  </div>
                  <BlockReasonBlock rows={stats.block_reasons} />
                </div>
              </Panel>

              <Panel className="min-w-0">
                <PanelHeader
                  title="Backtest"
                  action={(
                    <Button type="button" size="sm" variant="secondary" disabled={!symbol || busy} onClick={runBacktest}>
                      Run backtest
                    </Button>
                  )}
                />
                <div className="grid gap-4 p-4">
                  {backtest ? (
                    <>
                      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius)] bg-[var(--line)] sm:grid-cols-4">
                        <div className="bg-[var(--background)] p-4">
                          <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Trades</p>
                          <p className="mt-1 font-mono text-xl font-bold">{backtest.summary.trades}</p>
                        </div>
                        <div className="bg-[var(--background)] p-4">
                          <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Win rate</p>
                          <p className="mt-1 font-mono text-xl font-bold">{formatNumber(backtest.summary.win_rate)}%</p>
                        </div>
                        <div className="bg-[var(--background)] p-4">
                          <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Realized</p>
                          <p className={`mt-1 font-mono text-xl font-bold ${pnlColor(backtest.summary.realized_pnl)}`}>{formatNumber(backtest.summary.realized_pnl)}</p>
                        </div>
                        <div className="bg-[var(--background)] p-4">
                          <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Total profit</p>
                          <p className={`mt-1 font-mono text-xl font-bold ${pnlColor(backtest.summary.total_profit)}`}>{formatNumber(backtest.summary.total_profit)}</p>
                        </div>
                      </div>
                      <div className="grid gap-2">
                        {backtest.trades.slice().reverse().slice(0, 8).map((trade, index) => (
                          <div key={`${trade.opened_at_ms}-${index}`} className="rounded-[var(--radius)] border border-[var(--line)] p-3 text-xs">
                            <div className="flex items-center justify-between gap-3">
                              <span className={trade.side === "LONG" ? "font-bold text-[var(--positive)]" : "font-bold text-[var(--negative)]"}>{trade.side}</span>
                              <span className={pnlColor(trade.realized_pnl)}>{formatNumber(trade.realized_pnl)} USDT</span>
                            </div>
                            <p className="mt-1 text-[var(--muted)]">{trade.close_reason}</p>
                            <p className="mt-1 text-[var(--muted)]">{trade.setup_tags.slice(0, 3).join(", ")}</p>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <EmptyChart label="Run a lightweight historical replay for the selected symbol." />
                  )}
                </div>
              </Panel>
            </div>

            <Panel className="min-w-0">
              <PanelHeader title="Recent trades" />
              <TradeTable trades={trades} limit={8} />
            </Panel>
          </div>
        )}
      </div>
    </AppShell>
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

function gradeTone(grade: string) {
  if (grade === "A") return "text-[var(--positive)]";
  if (grade === "B") return "text-[var(--accent)]";
  if (grade === "C") return "text-[var(--warning)]";
  return "text-[var(--muted)]";
}

function BlockReasonBlock({ rows }: { rows: { reason: string; count: number; symbols: string[]; last_seen: string }[] }) {
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
