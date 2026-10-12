"use client";

import {
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ExcursionPoint, LevelSweep, LevelSweepCell } from "@/lib/types";

const tooltipStyle = {
  background: "#171b20",
  border: "1px solid #3b434d",
  borderRadius: 8,
  fontSize: 12,
};

// A winner that went this deep against itself nearly hit the stop; a loser that
// went this far in favor was a winner the exits gave back.
const NEAR_STOP_R = 0.8;
const GAVE_BACK_R = 0.7;
const MAX_AMBIGUOUS_PCT = 25;

function Empty({ text }: { text: string }) {
  return <div className="grid min-h-20 place-items-center px-3 text-center text-xs text-[var(--muted)]">{text}</div>;
}

function share(part: number, whole: number) {
  return whole ? `${Math.round((part / whole) * 100)}%` : "–";
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: ExcursionPoint }[] }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div style={tooltipStyle} className="px-2.5 py-2 text-[var(--text)]">
      <div className="font-semibold">{point.symbol} · {point.side}</div>
      <div className="mt-1 font-mono text-[11px]">
        MAE {point.mae_r.toFixed(2)}R · MFE {point.mfe_r.toFixed(2)}R
        {point.r !== null ? ` · result ${point.r > 0 ? "+" : ""}${point.r.toFixed(2)}R` : ""}
      </div>
      {point.close_reason ? <div className="mt-1 max-w-64 text-[11px] text-[var(--muted)]">{point.close_reason}</div> : null}
    </div>
  );
}

// Losses use a cross so win/loss identity is never carried by color alone.
function CrossShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return (
    <path
      d={`M${cx - 4},${cy - 4}L${cx + 4},${cy + 4}M${cx - 4},${cy + 4}L${cx + 4},${cy - 4}`}
      stroke="var(--negative)"
      strokeWidth={2}
      strokeLinecap="round"
    />
  );
}

export function ExcursionScatter({ points }: { points: ExcursionPoint[] }) {
  if (!points.length) {
    return <Empty text="No closed trades with excursion data in this range." />;
  }
  const wins = points.filter((p) => p.outcome === "win");
  const losses = points.filter((p) => p.outcome === "loss");
  const flats = points.filter((p) => p.outcome === "flat");
  const nearStop = wins.filter((p) => p.mae_r >= NEAR_STOP_R).length;
  const gaveBack = losses.filter((p) => p.mfe_r >= GAVE_BACK_R).length;
  const straightLosers = losses.filter((p) => p.mfe_r < 0.2).length;

  const readings = [
    {
      value: share(nearStop, wins.length),
      label: `of winners dipped ≥ ${NEAR_STOP_R}R first`,
      hint: "High: the stop sits at the edge of normal noise. A slightly wider stop keeps more of these.",
    },
    {
      value: share(gaveBack, losses.length),
      label: `of losers were ≥ +${GAVE_BACK_R}R first`,
      hint: "High: TP1 is too far or breakeven moves too late — profit was there and was given back.",
    },
    {
      value: share(straightLosers, losses.length),
      label: "of losers never went 0.2R in favor",
      hint: "High: the entry itself is wrong (timing or direction) — look at gates, not exits.",
    },
  ];

  return (
    <div>
      <div className="h-80 px-2 pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 4 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" />
            <XAxis
              type="number"
              dataKey="mae_r"
              name="MAE"
              domain={[0, "auto"]}
              tick={{ fill: "var(--muted)", fontSize: 10 }}
              stroke="var(--line-strong)"
              label={{ value: "Worst move against (MAE, R)", position: "insideBottom", offset: -14, fill: "var(--muted)", fontSize: 10 }}
            />
            <YAxis
              type="number"
              dataKey="mfe_r"
              name="MFE"
              domain={[0, "auto"]}
              tick={{ fill: "var(--muted)", fontSize: 10 }}
              stroke="var(--line-strong)"
              width={44}
              label={{ value: "Best move in favor (MFE, R)", angle: -90, position: "insideLeft", offset: 10, fill: "var(--muted)", fontSize: 10, style: { textAnchor: "middle" } }}
            />
            <ReferenceLine x={1} stroke="var(--line-strong)" strokeDasharray="4 4" label={{ value: "initial stop", position: "top", fill: "var(--muted)", fontSize: 10 }} />
            <ReferenceLine y={1} stroke="var(--line-strong)" strokeDasharray="4 4" label={{ value: "+1R", position: "right", fill: "var(--muted)", fontSize: 10 }} />
            <Tooltip content={<PointTooltip />} cursor={{ stroke: "var(--line-strong)", strokeDasharray: "2 2" }} />
            <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
            <Scatter name={`Win (${wins.length})`} data={wins} fill="var(--positive)" stroke="var(--background)" strokeWidth={2} />
            <Scatter name={`Loss (${losses.length})`} data={losses} fill="var(--negative)" shape={<CrossShape />} legendType="cross" />
            {flats.length ? <Scatter name={`Flat (${flats.length})`} data={flats} fill="var(--muted)" legendType="diamond" shape="diamond" /> : null}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="grid gap-px border-t border-[var(--line)] bg-[var(--line)] sm:grid-cols-3">
        {readings.map((item) => (
          <div key={item.label} className="bg-[var(--background)] p-3">
            <div className="text-base font-semibold">
              {item.value} <span className="text-xs font-normal text-[var(--muted)]">{item.label}</span>
            </div>
            <div className="mt-1 text-[10px] leading-4 text-[var(--muted)]">{item.hint}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Diverging scale around 0R: green for positive expectancy, red for negative,
// neutral gray near zero. Steps rather than a continuous ramp so cells stay legible.
function cellTone(cell: LevelSweepCell) {
  const e = cell.expectancy_r;
  if (e === null) return "bg-[var(--surface)]";
  if (e >= 0.3) return "bg-[var(--positive)]/45";
  if (e >= 0.1) return "bg-[var(--positive)]/25";
  if (e > -0.1) return "bg-[var(--surface-raised)]";
  if (e > -0.3) return "bg-[var(--negative)]/25";
  return "bg-[var(--negative)]/45";
}

function signedR(value: number | null) {
  if (value === null) return "–";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}R`;
}

function cellTitle(cell: LevelSweepCell) {
  return [
    `Stop ${cell.stop_atr} ATR · target ${cell.target_r}R`,
    `Expectancy ${signedR(cell.expectancy_r)} per trade (after fees)`,
    `Worst case ${signedR(cell.worst_case_r)} (every ambiguous counted as a loss)`,
    `Win rate ${cell.win_rate === null ? "–" : `${cell.win_rate.toFixed(0)}%`} of ${cell.decided} decided`,
    `Ambiguous ${cell.ambiguous_pct ?? 0}% · open at window end ${cell.open_pct ?? 0}% · ${cell.samples} samples`,
    cell.low_sample ? "LOW SAMPLE — treat as noise" : "",
  ].filter(Boolean).join("\n");
}

export function LevelHeatmap({ data }: { data: LevelSweep }) {
  if (!data.samples) {
    return (
      <Empty
        text={
          data.skipped_no_atr
            ? `${data.skipped_no_atr} resolved decisions have no ATR recorded. New decisions store it automatically; check back after the outcome window passes.`
            : "No resolved decisions in this range yet."
        }
      />
    );
  }
  const byKey = new Map(data.cells.map((c) => [`${c.stop_atr}|${c.target_r}`, c]));
  const isBest = (c: LevelSweepCell) => data.best?.stop_atr === c.stop_atr && data.best?.target_r === c.target_r;

  return (
    <div>
      <div className="overflow-x-auto p-3">
        <table className="w-full min-w-[560px] border-separate border-spacing-0.5 text-xs">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left text-[10px] font-normal uppercase tracking-[0.08em] text-[var(--muted)]">
                Stop ↓ · Target →
              </th>
              {data.targets_r.map((t) => (
                <th key={t} className="px-2 py-1 text-center font-mono text-[10px] font-normal text-[var(--muted)]">{t}R</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.stops_atr.map((s) => (
              <tr key={s}>
                <th className="px-2 py-1 text-left font-mono text-[10px] font-normal text-[var(--muted)]">{s} ATR</th>
                {data.targets_r.map((t) => {
                  const cell = byKey.get(`${s}|${t}`);
                  if (!cell) return <td key={t} />;
                  const uncertain = cell.low_sample || (cell.ambiguous_pct ?? 0) > MAX_AMBIGUOUS_PCT;
                  return (
                    <td
                      key={t}
                      title={cellTitle(cell)}
                      aria-label={cellTitle(cell)}
                      className={`${cellTone(cell)} rounded px-1 py-1.5 text-center ${uncertain ? "opacity-45 outline-1 outline-dashed -outline-offset-1 outline-[var(--line-strong)]" : ""} ${isBest(cell) ? "outline-2 outline-[var(--accent)]" : ""}`}
                    >
                      <div className="font-mono text-[11px] font-semibold text-[var(--text)]">{signedR(cell.expectancy_r)}</div>
                      <div className="text-[9px] text-[var(--muted)]">
                        {cell.win_rate === null ? "–" : `${cell.win_rate.toFixed(0)}% WR`}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line)] px-3 py-2 text-[10px] text-[var(--muted)]">
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--positive)]/45" /> ≥ +0.3R</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--positive)]/25" /> +0.1 to +0.3R</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--surface-raised)]" /> ±0.1R</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--negative)]/25" /> −0.1 to −0.3R</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm bg-[var(--negative)]/45" /> ≤ −0.3R</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm outline-1 outline-dashed outline-[var(--line-strong)] opacity-45" /> low sample or &gt;{MAX_AMBIGUOUS_PCT}% ambiguous</span>
        <span className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm outline-2 outline-[var(--accent)]" /> best reliable cell</span>
      </div>
      <p className="border-t border-[var(--line)] px-3 py-2 text-[10px] leading-4 text-[var(--muted)]">
        {data.samples} decisions replayed{data.skipped_no_atr ? ` (${data.skipped_no_atr} skipped: no ATR recorded)` : ""}.
        Expectancy is per trade in R of that stop, after a {data.fee_round_trip_pct.toFixed(2)}% round-trip fee — tight
        stops pay proportionally more. Only the window&apos;s best and worst move are stored, not their order: when both
        levels were reached the result is ambiguous (hover a cell for the worst case). Windows that reached neither level
        are excluded; use the 24h window to keep that share small. Single-target replay — partial take-profits, breakeven
        moves and trailing are not modelled.
      </p>
    </div>
  );
}
