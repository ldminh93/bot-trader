import type { Trade } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

function tradeGrade(trade: Trade): string {
  const fromPayload = trade.replay_payload?.trade_grade;
  if (fromPayload) return fromPayload.toUpperCase();
  const tag = (trade.setup_tags ?? []).find((t) => t.startsWith("grade:"));
  return tag ? tag.split(":")[1].toUpperCase() : "";
}

function gradeBadgeClass(grade: string): string {
  if (grade === "A") return "bg-[var(--positive)]/15 text-[var(--positive)]";
  if (grade === "B") return "bg-[var(--accent)]/15 text-[var(--accent)]";
  if (grade === "C") return "bg-yellow-500/15 text-yellow-500";
  return "bg-[var(--surface-raised)] text-[var(--muted)]";
}

export function TradeTable({
  trades,
  limit,
  onSelect,
  selectedTradeId,
}: {
  trades: Trade[];
  limit?: number;
  onSelect?: (trade: Trade) => void;
  selectedTradeId?: number | null;
}) {
  const rows = limit ? trades.slice(0, limit) : trades;
  if (!rows.length) {
    return (
      <div className="grid min-h-40 place-items-center px-6 text-center">
        <div>
          <p className="font-semibold">No executions yet</p>
          <p className="mt-1 text-sm text-[var(--muted)]">Start a paper bot to populate trade history.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[760px] text-left text-xs">
        <thead className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">
          <tr className="border-b border-[var(--line)]">
            <th className="px-4 py-3">Symbol</th>
            <th className="px-3 py-3">Side</th>
            <th className="px-3 py-3">Entry</th>
            <th className="px-3 py-3">Leverage</th>
            <th className="px-3 py-3">Exit</th>
            <th className="px-3 py-3">PnL</th>
            <th className="px-3 py-3">Margin ROI</th>
            <th className="px-3 py-3">Grade</th>
            <th className="px-3 py-3">Setup tags</th>
            <th className="px-3 py-3">Status</th>
            <th className="px-4 py-3 text-right">Opened</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((trade) => (
            <tr
              key={trade.id}
              className={`border-b border-[var(--line)] last:border-0 hover:bg-[var(--surface-raised)] ${selectedTradeId === trade.id ? "bg-[var(--accent)]/[0.07]" : ""} ${onSelect ? "cursor-pointer" : ""}`}
              onClick={() => onSelect?.(trade)}
            >
              <td className="px-4 py-3 font-mono font-semibold">{trade.symbol}</td>
              <td className={`px-3 py-3 font-bold ${trade.side === "LONG" ? "text-[var(--positive)]" : "text-[var(--negative)]"}`}>
                {trade.side}
              </td>
              <td className="px-3 py-3 font-mono">{formatNumber(trade.entry_price, 4)}</td>
              <td className="px-3 py-3 font-mono">x{trade.leverage}</td>
              <td className="px-3 py-3 font-mono">{trade.exit_price ? formatNumber(trade.exit_price, 4) : "-"}</td>
              <td className={`px-3 py-3 font-mono font-semibold ${pnlColor(Number(trade.realized_pnl) + Number(trade.unrealized_pnl))}`}>
                {formatNumber(Number(trade.realized_pnl) + Number(trade.unrealized_pnl))}
              </td>
              <td className={`px-3 py-3 font-mono ${pnlColor(trade.pnl_percent)}`}>{formatNumber(trade.pnl_percent)}%</td>
              <td className="px-3 py-3">
                {(() => { const g = tradeGrade(trade); return g ? (
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${gradeBadgeClass(g)}`}>{g}</span>
                ) : <span className="text-[var(--muted)]">—</span>; })()}
              </td>
              <td className="px-3 py-3 text-[10px] text-[var(--muted)]">
                {(trade.setup_tags ?? []).slice(0, 3).join(", ") || "-"}
              </td>
              <td className="px-3 py-3 text-[var(--muted)]">{trade.status}</td>
              <td className="px-4 py-3 text-right text-[var(--muted)]">
                {new Date(trade.opened_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
