"use client";

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
import { formatNumber } from "@/lib/utils";

const tooltipStyle = {
  background: "#171b20",
  border: "1px solid #3b434d",
  borderRadius: 8,
  fontSize: 12,
};

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
  const data = candles.slice(-60).map((item) => ({
    ...item,
    range: [item.low, item.high] as [number, number],
    time: new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  }));
  const positionCandle = position && data.length
    ? data.reduce((closest, candle) => {
        const openedAt = new Date(position.opened_at).getTime();
        return Math.abs(candle.timestamp - openedAt) < Math.abs(closest.timestamp - openedAt)
          ? candle
          : closest;
      })
    : null;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -10 }}>
        <CartesianGrid stroke="#282e35" vertical={false} />
        <XAxis dataKey="time" stroke="#69727d" tickLine={false} axisLine={false} minTickGap={32} fontSize={10} />
        <YAxis
          stroke="#69727d"
          tickLine={false}
          axisLine={false}
          domain={["dataMin", "dataMax"]}
          tickFormatter={(value) => formatNumber(value, value < 1 ? 4 : 0)}
          fontSize={10}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: "#f2f3ee" }}
          formatter={(value, name, item) => {
            if (name === "Candle") {
              const candle = item.payload as Candle;
              return [
                `O ${formatNumber(candle.open, 4)}  H ${formatNumber(candle.high, 4)}  L ${formatNumber(candle.low, 4)}  C ${formatNumber(candle.close, 4)}`,
                "OHLC",
              ];
            }
            return [formatNumber(Number(value), 4), name];
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10, color: "#929aa4" }} />
        <Bar dataKey="range" name="Candle" shape={<Candlestick />} isAnimationActive={false} />
        <Line type="monotone" dataKey="close" name="Close" stroke="#f2f3ee" strokeOpacity={0.35} strokeWidth={1} dot={false} />
        <Line type="monotone" dataKey="ma7" name="MA7" stroke="#f0b90b" strokeWidth={1.2} dot={false} />
        <Line type="monotone" dataKey="ma25" name="MA25" stroke="#55a3e8" strokeWidth={1.2} dot={false} />
        <Line type="monotone" dataKey="ma99" name="MA99" stroke="#d175d8" strokeWidth={1.2} dot={false} />
        {position && positionCandle && (
          <ReferenceDot
            x={positionCandle.time}
            y={Number(position.entry_price)}
            ifOverflow="extendDomain"
            shape={<PositionFlag side={position.side} />}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
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
