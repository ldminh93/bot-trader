"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import type {
  Diagnostics,
  DiagnosticsGateRow,
  DiagnosticsMode,
  DiagnosticsTradeRow,
  DiagnosticsWindow,
} from "@/lib/types";

const GATE_LABELS: Record<string, string> = {
  below_score_threshold: "Score below threshold",
  pullback_zone: "Not in MA25 pullback zone",
  rejection_candle: "No rejection candle",
  extended_move: "Extended move (chasing)",
  rsi_oversold: "RSI oversold (SHORT)",
  ma_alignment: "MA alignment",
  macro_direction: "Macro direction (MA99)",
  entry_location: "Entry too far from MA",
  circuit_breaker: "Consecutive-loss circuit breaker",
  opposite_unconfirmed: "Opposite entry unconfirmed",
  daily_loss: "Daily loss limit",
  max_positions: "Max open positions",
  atr_min: "ATR too quiet",
  atr_spike: "ATR spike",
  regime_choppy: "Choppy / pullback regime",
  reversal_high_vol: "MA-stack reversal in high volatility",
  suppressed_tag: "Losing setup tag suppressed",
  suppressed_symbol: "Losing symbol suppressed",
  min_confidence: "Below minimum confidence",
  funding: "Funding rate",
  tf_alignment: "Timeframe alignment score",
  sl_cooldown: "Re-entry cooldown after SL",
  volume_spike: "Volume spike required",
  ma7_slope: "MA7 slope too flat",
  sideway_block: "Sideway trend blocked",
  trend_alignment: "Higher-TF trend alignment",
  htf_confirm: "Higher-TF not confirmed",
  bias_4h: "4H bias mismatch",
  oi_confirm: "Open interest confirmation",
  volume_confirm: "Volume confirmation",
  ma7_slope_confirm: "MA7 slope confirmation",
  funding_confirm: "Funding confirmation",
  margin_insufficient: "Margin exceeds balance",
  risk_limit: "Risk limit exceeded",
  existing_position: "Existing exchange position",
  exchange_position: "Existing exchange position",
};

const MODES: DiagnosticsMode[] = ["all", "paper", "live"];
const WINDOWS: DiagnosticsWindow[] = ["1h", "4h", "24h"];

function isoDay(date: Date) {
  return date.toISOString().slice(0, 10);
}

function daysAgo(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return isoDay(date);
}

const dash = <span className="text-[var(--muted)]">–</span>;

function pct(value: number | null) {
  return value === null ? dash : <>{value.toFixed(0)}%</>;
}

function rValue(value: number | null) {
  if (value === null) return dash;
  const cls = value > 0 ? "text-[var(--positive)]" : value < 0 ? "text-[var(--negative)]" : "";
  return <span className={`font-mono ${cls}`}>{value > 0 ? "+" : ""}{value.toFixed(2)}R</span>;
}

function LowSample({ show, min }: { show: boolean; min: number }) {
  if (!show) return null;
  return (
    <span
      title={`Fewer than ${min} samples — treat as noise, not evidence`}
      className="ml-2 rounded border border-[var(--line)] px-1 py-px text-[9px] uppercase tracking-[0.08em] text-[var(--muted)]"
    >
      low sample
    </span>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-[var(--radius)] border border-[var(--line)]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
        <span>{title}</span>
        {hint ? <span className="normal-case font-normal">{hint}</span> : null}
      </div>
      {children}
    </section>
  );
}

const th = "px-3 py-2 text-right";

function Empty({ text }: { text: string }) {
  return <div className="grid min-h-20 place-items-center px-3 text-center text-xs text-[var(--muted)]">{text}</div>;
}

function GateTable({ rows, min }: { rows: DiagnosticsGateRow[]; min: number }) {
  if (!rows.length) {
    return <Empty text="No rejected entries recorded in this range yet. Decisions appear as the bot evaluates candidates." />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
          <tr className="border-b border-[var(--line)]">
            <th className="px-3 py-2 text-left">Gate</th>
            <th className={th}>Blocked</th>
            <th className={th} title="Blocked entries whose outcome window has finished">Resolved</th>
            <th className={th} title="First take-profit reached before the stop — the gate blocked a winner">Would win</th>
            <th className={th} title="Stop reached first — the gate blocked a loser">Would lose</th>
            <th className={th} title="Both levels in one candle, or neither reached">Undecided</th>
            <th className={th} title="Positive: the gate saved R by blocking losers. Negative: it cost R by blocking winners.">Net R</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.gate} className="border-b border-[var(--line)] last:border-0">
              <td className="px-3 py-2 text-left">
                {GATE_LABELS[row.gate] ?? row.gate}
                <LowSample show={row.low_sample} min={min} />
              </td>
              <td className="px-3 py-2 text-right font-mono">{row.blocked}</td>
              <td className="px-3 py-2 text-right font-mono">{row.resolved}</td>
              <td className="px-3 py-2 text-right">{pct(row.would_win_pct)}</td>
              <td className="px-3 py-2 text-right">{pct(row.would_lose_pct)}</td>
              <td className="px-3 py-2 text-right">{pct(row.undecided_pct)}</td>
              <td className="px-3 py-2 text-right">{rValue(row.net_r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeRowsTable({ rows, first, min }: { rows: DiagnosticsTradeRow[]; first: string; min: number }) {
  if (!rows.length) return <Empty text="No closed trades in this range." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
          <tr className="border-b border-[var(--line)]">
            <th className="px-3 py-2 text-left">{first}</th>
            <th className={th}>Trades</th>
            <th className={th}>Win %</th>
            <th className={th} title="Average R-multiple (realized PnL ÷ initial risk)">Avg R</th>
            <th className={th} title="Expected R per trade">Expectancy</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-[var(--line)] last:border-0">
              <td className="px-3 py-2 text-left">
                {row.label}
                <LowSample show={row.low_sample} min={min} />
              </td>
              <td className="px-3 py-2 text-right font-mono">{row.trades}</td>
              <td className="px-3 py-2 text-right">{pct(row.win_rate)}</td>
              <td className="px-3 py-2 text-right">{rValue(row.avg_r)}</td>
              <td className="px-3 py-2 text-right">{rValue(row.expectancy_r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExitQuality({ data, min }: { data: Diagnostics["exit_quality"]; min: number }) {
  if (!data.trades_with_excursion) {
    return <Empty text="No trades with excursion data yet. New trades record it automatically; older trades cannot be backfilled." />;
  }
  const items: { label: string; value: ReactNode; hint: string }[] = [
    { label: "Trades with excursion data", value: data.trades_with_excursion, hint: "Trades opened after this feature shipped" },
    { label: "Avg give-back from peak", value: rValue(data.avg_giveback_r), hint: "Peak favorable move (MFE) minus final R. High = exits leave profit behind." },
    { label: "Stopped-out trades", value: data.stopped_trades, hint: "Closed by a stop" },
    { label: "Stopped after being in profit", value: pct(data.stopped_after_favorable_pct), hint: "Share of stopped trades that were at least +0.5R first" },
    { label: "Winners' avg drawdown (MAE)", value: rValue(data.winners_avg_mae_r), hint: "Heat winners took before working. Well under 1R means a tighter stop was viable." },
    { label: "Losers' avg peak (MFE)", value: rValue(data.losers_avg_mfe_r), hint: "How far losers went right first. High means early profit-taking/breakeven may help." },
  ];
  return (
    <div className="grid gap-px bg-[var(--line)] sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <div key={item.label} className="bg-[var(--background)] p-3" title={item.hint}>
          <div className="text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">{item.label}</div>
          <div className="mt-1 text-base font-semibold">{item.value}</div>
          <div className="mt-1 text-[10px] text-[var(--muted)]">{item.hint}</div>
        </div>
      ))}
      {data.low_sample ? (
        <div className="bg-[var(--background)] p-3 text-[10px] text-[var(--muted)] sm:col-span-2 lg:col-span-3">
          Fewer than {min} trades have excursion data — these figures are indicative only.
        </div>
      ) : null}
    </div>
  );
}

export function DiagnosticsConsole() {
  const [start, setStart] = useState(() => daysAgo(30));
  const [end, setEnd] = useState(() => isoDay(new Date()));
  const [mode, setMode] = useState<DiagnosticsMode>("all");
  const [window_, setWindow] = useState<DiagnosticsWindow>("4h");
  const [data, setData] = useState<Diagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const latest = useRef(0);

  const load = useCallback(async () => {
    const ticket = ++latest.current;
    setLoading(true);
    try {
      const result = await api.diagnostics(start, end, mode, window_);
      if (ticket !== latest.current) return;
      setData(result);
      setError("");
    } catch (reason) {
      if (ticket !== latest.current) return;
      setError(reason instanceof Error ? reason.message : "Unable to load diagnostics");
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  }, [start, end, mode, window_]);

  useEffect(() => {
    void load();
  }, [load]);

  const min = data?.min_sample ?? 30;
  const empty = data !== null && data.data_notes.decisions_total === 0 && data.data_notes.trades_total === 0;
  const control = "rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-xs";

  return (
    <AppShell>
      <header className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)]/95 px-4 py-4 backdrop-blur md:px-6">
        <h1 className="text-lg font-bold">Diagnostics</h1>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Evidence for tuning: does each gate earn its keep, is the score calibrated, where do exits leak R
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            From <input type="date" className={control} value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="flex items-center gap-1">
            To <input type="date" className={control} value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <label className="flex items-center gap-1">
            Mode
            <select className={control} value={mode} onChange={(e) => setMode(e.target.value as DiagnosticsMode)}>
              {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1" title="How long after the blocked entry the outcome is judged">
            Outcome window
            <select className={control} value={window_} onChange={(e) => setWindow(e.target.value as DiagnosticsWindow)}>
              {WINDOWS.map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </label>
        </div>
      </header>

      <div className="grid gap-4 p-4 md:p-6">
        {error && (
          <div className="rounded-[var(--radius)] border border-[var(--negative)]/40 bg-[var(--negative)]/10 p-3 text-sm text-[#ff9b9b]">
            {error}
          </div>
        )}
        {loading && !data ? (
          <div className="h-48 animate-pulse rounded-[var(--radius)] bg-[var(--surface)]" />
        ) : data ? (
          <div className={`grid gap-4 ${loading ? "opacity-60" : ""}`}>
            {empty ? (
              <div className="rounded-[var(--radius)] border border-[var(--line)] p-4 text-sm text-[var(--muted)]">
                No decisions or closed trades in this range yet. Keep the bot running — outcomes fill in after 1h / 4h / 24h,
                and rows need {min}+ samples before they stop being flagged.
              </div>
            ) : null}

            <Section title="Gate value" hint="Would the blocked entries have won? Judged at the selected outcome window">
              <GateTable rows={data.gates} min={min} />
            </Section>

            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Calibration by confidence score" hint="Higher bands should earn more R">
                <TradeRowsTable rows={data.calibration.by_score_bucket} first="Score band" min={min} />
              </Section>
              <Section title="Calibration by grade" hint="A should beat B should beat C">
                <TradeRowsTable rows={data.calibration.by_grade} first="Grade" min={min} />
              </Section>
              <Section title="Expectancy by setup tag">
                <TradeRowsTable rows={data.expectancy.by_tag} first="Tag" min={min} />
              </Section>
              <Section title="Expectancy by regime × side">
                <TradeRowsTable rows={data.expectancy.by_regime_side} first="Regime / side" min={min} />
              </Section>
            </div>

            <Section title="Exit quality" hint="MFE = best move in favor, MAE = worst move against, both in R">
              <ExitQuality data={data.exit_quality} min={min} />
            </Section>

            <p className="text-[10px] text-[var(--muted)]">
              {data.data_notes.decisions_total} decisions · {data.data_notes.trades_total} closed trades. Score = {data.data_notes.score_metric}.
              Excursion is sampled per {data.data_notes.excursion_granularity}, so brief wicks between cycles are missed.
              Rejections that never reached risk planning use a default 1.5×ATR stop and 1R target. Decisions come from the
              master (admin) account, which is the only one that evaluates entries.
            </p>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
