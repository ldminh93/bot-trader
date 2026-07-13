"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Candle, Trade, TradeStats } from "@/lib/types";
import { formatNumber, formatPrice } from "@/lib/utils";

const tooltipStyle = {
  background: "#171b20",
  border: "1px solid #3b434d",
  borderRadius: 8,
  fontSize: 12,
};

const DEFAULT_PRICE_WINDOW = 80;
const MIN_PRICE_WINDOW = 35;
const MAX_PRICE_WINDOW = 160;

interface CandleShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: Candle & { range: [number, number] };
}

function Candlestick({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  payload,
}: CandleShapeProps) {
  if (!payload) return null;

  const { open, close, high, low } = payload;
  const priceRange = Math.max(high - low, Number.EPSILON);
  const centerX = x + width / 2;
  const bodyWidth = Math.max(3, Math.min(width * 0.68, 10));
  const bodyX = centerX - bodyWidth / 2;
  const bodyHigh = Math.max(open, close);
  const bodyLow = Math.min(open, close);
  const bodyY = y + ((high - bodyHigh) / priceRange) * height;
  const calculatedBodyHeight = ((bodyHigh - bodyLow) / priceRange) * height;
  const bodyHeight = Math.max(2, calculatedBodyHeight);
  const color = close >= open ? "#43c987" : "#f06464";

  return (
    <g>
      <line x1={centerX} x2={centerX} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect
        x={bodyX}
        y={bodyY}
        width={bodyWidth}
        height={bodyHeight}
        fill={color}
        stroke={color}
        rx={1}
      />
    </g>
  );
}

interface ExitFlagProps {
  cx?: number;
  cy?: number;
  isWin: boolean;
}

function ExitFlag({ cx = 0, cy = 0, isWin }: ExitFlagProps) {
  const color = isWin ? "#43c987" : "#f06464";
  return (
    <g aria-label={isWin ? "Winning exit" : "Losing exit"}>
      <line x1={cx} y1={cy - 14} x2={cx} y2={cy + 14} stroke={color} strokeWidth={1.5} strokeDasharray="2 2" />
      <rect
        x={cx - 5}
        y={cy - 5}
        width={10}
        height={10}
        fill="#111418"
        stroke={color}
        strokeWidth={2}
        transform={`rotate(45 ${cx} ${cy})`}
      />
      <text x={cx} y={cy - 20} fill={color} fontSize={10} fontWeight={700} textAnchor="middle">
        {isWin ? "WIN" : "LOSS"}
      </text>
    </g>
  );
}

interface PositionFlagProps {
  cx?: number;
  cy?: number;
  side: Trade["side"];
}

function PositionFlag({ cx = 0, cy = 0, side }: PositionFlagProps) {
  const color = side === "LONG" ? "#43c987" : "#f06464";
  const labelX = side === "LONG" ? cx + 12 : cx - 12;
  const textAnchor = side === "LONG" ? "start" : "end";

  return (
    <g aria-label={`${side} position entry`}>
      <line x1={cx} y1={cy + 10} x2={cx} y2={cy - 14} stroke={color} strokeWidth={2} />
      <path
        d={
          side === "LONG"
            ? `M ${cx} ${cy - 14} L ${cx + 13} ${cy - 9} L ${cx} ${cy - 4} Z`
            : `M ${cx} ${cy - 14} L ${cx - 13} ${cy - 9} L ${cx} ${cy - 4} Z`
        }
        fill={color}
      />
      <circle cx={cx} cy={cy} r={3} fill="#111418" stroke={color} strokeWidth={2} />
      <text
        x={labelX}
        y={cy + 4}
        fill={color}
        fontSize={10}
        fontWeight={700}
        textAnchor={textAnchor}
      >
        {side}
      </text>
    </g>
  );
}

export function PriceChart({
  candles,
  position,
}: {
  candles: Candle[];
  position?: Trade;
}) {
  const [windowSize, setWindowSize] = useState(DEFAULT_PRICE_WINDOW);
  const [offsetFromEnd, setOffsetFromEnd] = useState(0);
  const dragRef = useRef<{ pointerId: number; startX: number; startOffset: number } | null>(null);

  const maxOffset = Math.max(candles.length - windowSize, 0);
  const clampedOffset = Math.min(offsetFromEnd, maxOffset);
  const startIndex = Math.max(candles.length - windowSize - clampedOffset, 0);
  const endIndex = candles.length - clampedOffset;
  const isLiveView = clampedOffset === 0;

  useEffect(() => {
    setOffsetFromEnd((current) => Math.min(current, Math.max(candles.length - windowSize, 0)));
  }, [candles.length, windowSize]);

  const data = useMemo(
    () =>
      candles.slice(startIndex, endIndex).map((item) => ({
        ...item,
        range: [item.low, item.high] as [number, number],
      })),
    [candles, startIndex, endIndex],
  );

  const positionCandle = position && data.length
    ? data.reduce((closest, candle) => {
        const openedAt = new Date(position.opened_at).getTime();
        return Math.abs(candle.timestamp - openedAt) < Math.abs(closest.timestamp - openedAt)
          ? candle
          : closest;
      })
    : null;

  const closeCandle = position && position.status === "CLOSED" && position.closed_at && data.length
    ? data.reduce((closest, candle) => {
        const closedAt = new Date(position.closed_at!).getTime();
        return Math.abs(candle.timestamp - closedAt) < Math.abs(closest.timestamp - closedAt)
          ? candle
          : closest;
      })
    : null;

  function moveWindow(nextOffset: number) {
    setOffsetFromEnd(Math.max(0, Math.min(nextOffset, Math.max(candles.length - windowSize, 0))));
  }

  function updateWindowSize(nextSize: number) {
    const size = Math.max(MIN_PRICE_WINDOW, Math.min(nextSize, Math.min(MAX_PRICE_WINDOW, Math.max(candles.length, MIN_PRICE_WINDOW))));
    setWindowSize(size);
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (candles.length <= windowSize) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startOffset: clampedOffset,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    const candleWidth = Math.max(event.currentTarget.clientWidth / Math.max(windowSize, 1), 6);
    const candleDelta = Math.round((event.clientX - dragRef.current.startX) / candleWidth);
    moveWindow(dragRef.current.startOffset + candleDelta);
  }

  function handlePointerUp(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function handleWheel(event: WheelEvent<HTMLDivElement>) {
    if (event.shiftKey) {
      event.preventDefault();
      updateWindowSize(windowSize + (event.deltaY > 0 ? 10 : -10));
      return;
    }
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      event.preventDefault();
      moveWindow(clampedOffset + Math.round(event.deltaX / 20));
    }
  }

  const btnBase =
    "rounded px-1.5 py-0.5 font-semibold text-[var(--text)] transition hover:bg-[var(--surface-raised)] active:scale-95 disabled:opacity-30 sm:px-2";

  return (
    <div className="flex h-full w-full min-w-0 select-none flex-col overflow-hidden">
      {/* Nav bar sits above the chart — never overlaps the tooltip */}
      <div className="flex shrink-0 items-center border-b border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            className={btnBase}
            onClick={() => moveWindow(clampedOffset + Math.max(Math.round(windowSize / 2), 1))}
            disabled={clampedOffset >= maxOffset}
            aria-label="Older candles"
          >
            <span className="hidden sm:inline">Older</span>
            <span className="sm:hidden">‹</span>
          </button>
          <button
            type="button"
            className={btnBase}
            onClick={() => moveWindow(clampedOffset - Math.max(Math.round(windowSize / 2), 1))}
            disabled={isLiveView}
            aria-label="Newer candles"
          >
            <span className="hidden sm:inline">Newer</span>
            <span className="sm:hidden">›</span>
          </button>
          <button type="button" className={btnBase} onClick={() => updateWindowSize(windowSize - 10)} aria-label="Zoom in">+</button>
          <button type="button" className={btnBase} onClick={() => updateWindowSize(windowSize + 10)} aria-label="Zoom out">−</button>
          <button
            type="button"
            className={`rounded px-1.5 py-0.5 font-semibold transition active:scale-95 sm:px-2 ${isLiveView ? "bg-[var(--positive)]/15 text-[var(--positive)]" : "text-[var(--text)] hover:bg-[var(--surface-raised)]"}`}
            onClick={() => moveWindow(0)}
          >
            Live
          </button>
        </div>
        {/* min-w-0 + flex-1 required for truncate to work inside a flex row */}
        <span className="min-w-0 flex-1 truncate pl-2 text-right">
          <span className="hidden sm:inline">Drag · Shift+wheel zoom · </span>
          {startIndex + 1}–{Math.max(endIndex, startIndex + 1)} / {candles.length} bars
        </span>
      </div>

      {/* Chart area — min-w-0 ensures ResponsiveContainer measures the correct width */}
      <div
        className={`min-h-0 min-w-0 flex-1 touch-none ${candles.length > windowSize ? "cursor-grab active:cursor-grabbing" : ""}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onWheel={handleWheel}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#282e35" vertical={false} />
            <XAxis
              dataKey="timestamp"
              stroke="#69727d"
              tickLine={false}
              axisLine={false}
              minTickGap={32}
              fontSize={10}
              tickFormatter={(ts: number) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            />
            <YAxis
              stroke="#69727d"
              tickLine={false}
              axisLine={false}
              domain={["dataMin", "dataMax"]}
              tickFormatter={(value) => formatPrice(value)}
              fontSize={10}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#f2f3ee" }}
              labelFormatter={(ts: number) =>
                new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
              }
              formatter={(value, name, item) => {
                if (name === "Candle") {
                  const candle = item.payload as Candle;
                  return [
                    `O ${formatPrice(candle.open)}  H ${formatPrice(candle.high)}  L ${formatPrice(candle.low)}  C ${formatPrice(candle.close)}`,
                    "OHLC",
                  ];
                }
                return [formatPrice(Number(value)), name];
              }}
            />
            <Legend wrapperStyle={{ fontSize: 10, color: "#929aa4" }} />
            <Bar dataKey="range" name="Candle" fill="#69727d" shape={<Candlestick />} isAnimationActive={false} />
            <Line type="monotone" dataKey="close" name="Close" stroke="#f2f3ee" strokeOpacity={0.35} strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="ma7" name="MA7" stroke="#f0b90b" strokeWidth={1.2} dot={false} />
            <Line type="monotone" dataKey="ma25" name="MA25" stroke="#55a3e8" strokeWidth={1.2} dot={false} />
            <Line type="monotone" dataKey="ma99" name="MA99" stroke="#d175d8" strokeWidth={1.2} dot={false} />
            {position && positionCandle && (
              <ReferenceDot
                x={positionCandle.timestamp}
                y={Number(position.entry_price)}
                ifOverflow="extendDomain"
                shape={<PositionFlag side={position.side} />}
              />
            )}
            {position && closeCandle && position.exit_price && (
              <ReferenceDot
                x={closeCandle.timestamp}
                y={Number(position.exit_price)}
                ifOverflow="extendDomain"
                shape={<ExitFlag isWin={Number(position.realized_pnl) > 0} />}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function FlowChart({ candles }: { candles: Candle[] }) {
  const data = candles.slice(-45).map((item) => ({
    ...item,
    time: new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="time" stroke="#69727d" tickLine={false} axisLine={false} minTickGap={38} fontSize={10} />
        <YAxis stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} tickFormatter={(value) => formatNumber(value, 0)} />
        <Tooltip contentStyle={tooltipStyle} />
        <Bar dataKey="delta" name="Delta" fill="#f0b90b" opacity={0.65} />
        <Line type="monotone" dataKey="cvd" name="CVD" stroke="#43c987" dot={false} strokeWidth={1.4} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function ProfitChart({ stats }: { stats: TradeStats }) {
  let cumulative = 0;
  const data = stats.daily.map((point) => {
    cumulative += Number(point.pnl);
    return { ...point, cumulative };
  });
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -8 }}>
        <defs>
          <linearGradient id="profitFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#43c987" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#43c987" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="day" stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} />
        <YAxis stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} />
        <Tooltip contentStyle={tooltipStyle} />
        <Area type="monotone" dataKey="cumulative" name="Cumulative PnL" stroke="#43c987" fill="url(#profitFill)" strokeWidth={1.5} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function DailyPnlChart({ stats }: { stats: TradeStats }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={stats.daily} margin={{ top: 10, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="day" stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} />
        <YAxis stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} />
        <Tooltip contentStyle={tooltipStyle} />
        <Bar dataKey="pnl" name="Daily PnL" fill="#f0b90b" />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function WinRateSparkline({ trades }: { trades: Trade[] }) {
  const closed = trades
    .filter((t) => t.status === "CLOSED")
    .slice()
    .reverse(); // oldest first

  if (closed.length < 2) {
    return <div className="grid h-full place-items-center text-xs text-[var(--muted)]">Need more trades for rolling win rate.</div>;
  }

  const WINDOW = 10;
  const data = closed.map((_, i) => {
    const slice = closed.slice(Math.max(0, i - WINDOW + 1), i + 1);
    const wins = slice.filter((t) => Number(t.realized_pnl) > 0).length;
    return {
      trade: i + 1,
      winRate: Math.round((wins / slice.length) * 100),
    };
  });

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -8 }}>
        <defs>
          <linearGradient id="wrFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#55a3e8" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#55a3e8" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="trade" stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} label={{ value: "trade #", position: "insideBottomRight", offset: -4, fontSize: 9, fill: "#69727d" }} />
        <YAxis stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}%`, `Rolling ${WINDOW}-trade win rate`]} />
        <Area type="monotone" dataKey="winRate" name={`Rolling ${WINDOW}-trade win rate`} stroke="#55a3e8" fill="url(#wrFill)" strokeWidth={1.5} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function closeCategory(reason: string): "tp" | "sl" | "early" | "manual" {
  const r = reason.toLowerCase();
  if (r.includes("take profit") || r.includes("tp3") || r.includes("trailing stop hit")) return "tp";
  if (r.includes("stop loss") || r.includes("trailing stop")) return "sl";
  if (r.includes("early exit")) return "early";
  return "manual";
}

export function PnlAttributionChart({ trades }: { trades: Trade[] }) {
  const closed = trades.filter((t) => t.status === "CLOSED" && t.closed_at);

  const byDay = new Map<string, { tp: number; sl: number; early: number; manual: number }>();
  for (const trade of closed) {
    const day = trade.closed_at!.slice(0, 10);
    const pnl = Number(trade.realized_pnl);
    const existing = byDay.get(day) ?? { tp: 0, sl: 0, early: 0, manual: 0 };
    existing[closeCategory(trade.close_reason)] += pnl;
    byDay.set(day, existing);
  }

  const data = Array.from(byDay.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-30)
    .map(([day, vals]) => ({
      day: day.slice(5), // MM-DD
      tp: Number(vals.tp.toFixed(2)),
      sl: Number(vals.sl.toFixed(2)),
      early: Number(vals.early.toFixed(2)),
      manual: Number(vals.manual.toFixed(2)),
    }));

  if (!data.length) {
    return <div className="grid h-full place-items-center text-xs text-[var(--muted)]">No closed trades to attribute.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="day" stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} />
        <YAxis stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [formatNumber(Number(v)), name]} />
        <Legend wrapperStyle={{ fontSize: 10, color: "#929aa4" }} />
        <Bar dataKey="tp" name="Take profit" stackId="pnl" fill="#43c987" />
        <Bar dataKey="early" name="Early exit" stackId="pnl" fill="#f0b90b" />
        <Bar dataKey="manual" name="Manual" stackId="pnl" fill="#55a3e8" />
        <Bar dataKey="sl" name="Stop loss" stackId="pnl" fill="#f06464" radius={[0, 0, 2, 2]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function PositioningChart({
  history,
}: {
  history: { created_at: string; open_interest: number; funding_rate: number }[];
}) {
  const data = history.map((point) => ({
    ...point,
    time: new Date(point.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    funding_percent: point.funding_rate * 100,
  }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -10 }}>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="time" stroke="#69727d" tickLine={false} axisLine={false} minTickGap={38} fontSize={10} />
        <YAxis yAxisId="oi" stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} tickFormatter={(value) => formatNumber(value, 0)} />
        <YAxis yAxisId="funding" orientation="right" stroke="#69727d" tickLine={false} axisLine={false} fontSize={10} tickFormatter={(value) => `${formatNumber(value, 3)}%`} />
        <Tooltip contentStyle={tooltipStyle} />
        <Line yAxisId="oi" type="monotone" dataKey="open_interest" name="Open interest" stroke="#55a3e8" dot={false} strokeWidth={1.4} />
        <Bar yAxisId="funding" dataKey="funding_percent" name="Funding %" fill="#f0b90b" opacity={0.55} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
