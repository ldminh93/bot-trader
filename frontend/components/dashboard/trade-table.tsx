import type { Trade } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

export function TradeTable({ trades, limit }: { trades: Trade[]; limit?: number }) {
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
    <>
      <div className="divide-y divide-[var(--line)] md:hidden">
        {rows.map((trade) => (
          <article key={trade.id} className="grid gap-3 px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-sm font-semibold">{trade.symbol}</p>
                <p className="mt-1 text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">
                  {new Date(trade.opened_at).toLocaleString()}
                </p>
              </div>
              <div className="text-right">
                <p className={`font-bold ${trade.side === "LONG" ? "text-[var(--positive)]" : "text-[var(--negative)]"}`}>
                  {trade.side}
                </p>
                <p className="mt-1 text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">{trade.status}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
              <div>
                <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Entry</p>
                <p className="mt-1 font-mono">{formatNumber(trade.entry_price, 4)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Exit</p>
                <p className="mt-1 font-mono">{trade.exit_price ? formatNumber(trade.exit_price, 4) : "-"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Leverage</p>
                <p className="mt-1 font-mono">x{trade.leverage}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">PnL</p>
                <p className={`mt-1 font-mono font-semibold ${pnlColor(Number(trade.realized_pnl) + Number(trade.unrealized_pnl))}`}>
                  {formatNumber(Number(trade.realized_pnl) + Number(trade.unrealized_pnl))}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">Margin ROI</p>
                <p className={`mt-1 font-mono ${pnlColor(trade.pnl_percent)}`}>{formatNumber(trade.pnl_percent)}%</p>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="hidden overflow-x-auto scrollbar-thin md:block">
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
              <th className="px-3 py-3">Status</th>
              <th className="px-4 py-3 text-right">Opened</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((trade) => (
              <tr key={trade.id} className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--surface-raised)]">
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
                <td className="px-3 py-3 text-[var(--muted)]">{trade.status}</td>
                <td className="px-4 py-3 text-right text-[var(--muted)]">
                  {new Date(trade.opened_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
