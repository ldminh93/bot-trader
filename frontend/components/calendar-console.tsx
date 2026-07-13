"use client";

import { CaretLeft, CaretRight, CalendarBlank } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api } from "@/lib/api";
import type { Trade } from "@/lib/types";
import { formatNumber, formatPrice, pnlColor } from "@/lib/utils";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

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

interface DaySummary {
  date: string; // "YYYY-MM-DD"
  trades: Trade[];
  totalPnl: number;
  wins: number;
  losses: number;
}

function buildDaySummaries(trades: Trade[]): Map<string, DaySummary> {
  const map = new Map<string, DaySummary>();
  for (const trade of trades) {
    // Group closed trades by closed_at date; open trades by opened_at
    const ts = trade.closed_at ?? trade.opened_at;
    const date = ts.slice(0, 10);
    const existing = map.get(date) ?? { date, trades: [], totalPnl: 0, wins: 0, losses: 0 };
    existing.trades.push(trade);
    if (trade.status === "CLOSED") {
      const pnl = Number(trade.realized_pnl);
      existing.totalPnl += pnl;
      if (pnl > 0) existing.wins++;
      else if (pnl < 0) existing.losses++;
    }
    map.set(date, existing);
  }
  return map;
}

function toLocalDateString(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function CalendarConsole() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [viewDate, setViewDate] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  useEffect(() => {
    void api.trades().then((data) => {
      setTrades(data);
      setLoading(false);
    });
  }, []);

  const summaries = useMemo(() => buildDaySummaries(trades), [trades]);

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const monthLabel = viewDate.toLocaleString("default", { month: "long", year: "numeric" });

  // Calendar grid: start on Sunday of the week containing the 1st
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = toLocalDateString(new Date());

  // Build flat array of cells (nulls for padding + day numbers)
  const cells: (number | null)[] = [
    ...Array<null>(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const selectedSummary = selectedDate ? (summaries.get(selectedDate) ?? null) : null;

  function prevMonth() {
    setViewDate(new Date(year, month - 1, 1));
    setSelectedDate(null);
  }
  function nextMonth() {
    setViewDate(new Date(year, month + 1, 1));
    setSelectedDate(null);
  }

  // Totals for the current month
  const monthTotals = useMemo(() => {
    let pnl = 0;
    let wins = 0;
    let losses = 0;
    for (const [key, summary] of summaries) {
      if (key.startsWith(`${year}-${String(month + 1).padStart(2, "0")}`)) {
        pnl += summary.totalPnl;
        wins += summary.wins;
        losses += summary.losses;
      }
    }
    return { pnl, wins, losses };
  }, [summaries, year, month]);

  const maxMonthPnl = useMemo(() => {
    let max = 0;
    const prefix = `${year}-${String(month + 1).padStart(2, "0")}`;
    for (const [key, summary] of summaries) {
      if (key.startsWith(prefix)) max = Math.max(max, Math.abs(summary.totalPnl));
    }
    return max;
  }, [summaries, year, month]);

  return (
    <AppShell>
      <header className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)]/95 px-4 py-3 backdrop-blur md:px-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <CalendarBlank size={20} className="text-[var(--accent)]" />
            <h1 className="font-bold">Trade Calendar</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={prevMonth}
              className="flex size-8 items-center justify-center rounded-[var(--radius)] border border-[var(--line-strong)] hover:bg-[var(--surface-raised)]"
            >
              <CaretLeft size={14} />
            </button>
            <span className="min-w-[148px] text-center text-sm font-semibold">{monthLabel}</span>
            <button
              onClick={nextMonth}
              className="flex size-8 items-center justify-center rounded-[var(--radius)] border border-[var(--line-strong)] hover:bg-[var(--surface-raised)]"
            >
              <CaretRight size={14} />
            </button>
          </div>
        </div>
      </header>

      <div className="p-4 md:p-6">
        {/* Month summary strip */}
        <div className="mb-4 grid grid-cols-3 overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)]">
          <div className="px-4 py-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">Month PnL</p>
            <p className={`mt-1 font-mono text-lg font-bold ${pnlColor(monthTotals.pnl)}`}>
              {formatNumber(monthTotals.pnl)} USDT
            </p>
          </div>
          <div className="border-x border-[var(--line)] px-4 py-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">Win days</p>
            <p className="mt-1 font-mono text-lg font-bold text-[var(--positive)]">{monthTotals.wins}</p>
          </div>
          <div className="px-4 py-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">Loss days</p>
            <p className="mt-1 font-mono text-lg font-bold text-[var(--negative)]">{monthTotals.losses}</p>
          </div>
        </div>

        <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_360px]">
          {/* Calendar grid */}
          <Panel className="min-w-0">
            <div className="p-3">
              {/* Day-of-week headers */}
              <div className="mb-1 grid grid-cols-7 gap-1">
                {DAYS.map((day) => (
                  <div key={day} className="py-1 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
                    {day}
                  </div>
                ))}
              </div>

              {/* Day cells */}
              <div className="grid grid-cols-7 gap-1">
                {cells.map((day, index) => {
                  if (day === null) {
                    return <div key={`pad-${index}`} />;
                  }
                  const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                  const summary = summaries.get(dateStr);
                  const isToday = dateStr === today;
                  const isSelected = dateStr === selectedDate;
                  const ratio = maxMonthPnl > 0 && summary && summary.totalPnl !== 0
                    ? Math.min(1, Math.abs(summary.totalPnl) / maxMonthPnl)
                    : 0;
                  const cellStyle = !isSelected && ratio > 0 ? {
                    backgroundColor: summary!.totalPnl >= 0
                      ? `rgba(34, 197, 94, ${(0.07 + ratio * 0.28).toFixed(2)})`
                      : `rgba(239, 68, 68, ${(0.07 + ratio * 0.28).toFixed(2)})`,
                  } : undefined;

                  return (
                    <button
                      key={dateStr}
                      type="button"
                      onClick={() => setSelectedDate(isSelected ? null : dateStr)}
                      style={cellStyle}
                      className={[
                        "flex min-h-[72px] flex-col rounded-[var(--radius)] border p-1.5 text-left transition-colors sm:min-h-[80px] sm:p-2",
                        isSelected
                          ? "border-[var(--accent)] bg-[var(--accent)]/[0.06]"
                          : "border-[var(--line)] hover:brightness-95",
                      ].join(" ")}
                    >
                      <span
                        className={[
                          "mb-1 flex size-6 items-center justify-center rounded-full text-xs font-bold",
                          isToday ? "bg-[var(--accent)] text-[var(--accent-ink)]" : "",
                        ].join(" ")}
                      >
                        {day}
                      </span>

                      {loading ? null : summary ? (
                        <div className="min-w-0 flex-1">
                          <p className={`truncate font-mono text-[11px] font-bold leading-tight ${pnlColor(summary.totalPnl)}`}>
                            {summary.totalPnl >= 0 ? "+" : ""}
                            {formatNumber(summary.totalPnl)}
                          </p>
                          <p className="mt-0.5 text-[10px] text-[var(--muted)]">
                            {summary.trades.length} trade{summary.trades.length !== 1 ? "s" : ""}
                          </p>
                          {summary.wins > 0 || summary.losses > 0 ? (
                            <p className="text-[10px]">
                              <span className="text-[var(--positive)]">{summary.wins}W</span>
                              {" / "}
                              <span className="text-[var(--negative)]">{summary.losses}L</span>
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </Panel>

          {/* Day detail panel */}
          <Panel className="h-fit min-w-0">
            <PanelHeader
              title={selectedDate
                ? new Date(selectedDate + "T00:00:00").toLocaleDateString("default", { weekday: "long", month: "long", day: "numeric", year: "numeric" })
                : "Day detail"}
            />

            {!selectedDate ? (
              <div className="grid min-h-48 place-items-center px-6 text-center">
                <p className="text-xs text-[var(--muted)]">Click a date on the calendar to see trades for that day.</p>
              </div>
            ) : !selectedSummary ? (
              <div className="grid min-h-48 place-items-center px-6 text-center">
                <p className="text-xs text-[var(--muted)]">No trades on this date.</p>
              </div>
            ) : (
              <div>
                {/* Day totals */}
                <div className="grid grid-cols-3 border-b border-[var(--line)]">
                  <div className="px-4 py-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">PnL</p>
                    <p className={`mt-1 font-mono text-sm font-bold ${pnlColor(selectedSummary.totalPnl)}`}>
                      {selectedSummary.totalPnl >= 0 ? "+" : ""}{formatNumber(selectedSummary.totalPnl)}
                    </p>
                  </div>
                  <div className="border-x border-[var(--line)] px-4 py-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">Trades</p>
                    <p className="mt-1 font-mono text-sm font-bold">{selectedSummary.trades.length}</p>
                  </div>
                  <div className="px-4 py-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">W / L</p>
                    <p className="mt-1 font-mono text-sm font-bold">
                      <span className="text-[var(--positive)]">{selectedSummary.wins}</span>
                      {" / "}
                      <span className="text-[var(--negative)]">{selectedSummary.losses}</span>
                    </p>
                  </div>
                </div>

                {/* Trade list */}
                <div className="divide-y divide-[var(--line)]">
                  {selectedSummary.trades.map((trade) => {
                    const pnl = Number(trade.realized_pnl);
                    return (
                      <div key={trade.id} className="px-4 py-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-bold">{trade.symbol}</span>
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                trade.side === "LONG"
                                  ? "bg-[var(--positive)]/15 text-[var(--positive)]"
                                  : "bg-[var(--negative)]/15 text-[var(--negative)]"
                              }`}
                            >
                              {trade.side}
                            </span>
                            {(() => { const g = tradeGrade(trade); return g ? (
                              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${gradeBadgeClass(g)}`}>{g}</span>
                            ) : null; })()}
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                                trade.status === "OPEN"
                                  ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                                  : trade.status === "CLOSED"
                                    ? "bg-[var(--surface-raised)] text-[var(--muted)]"
                                    : "bg-[var(--warning)]/15 text-[var(--warning)]"
                              }`}
                            >
                              {trade.status}
                            </span>
                          </div>
                          <span className={`font-mono text-sm font-bold ${pnlColor(pnl)}`}>
                            {pnl >= 0 ? "+" : ""}{formatNumber(pnl)} USDT
                          </span>
                        </div>

                        <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-[var(--muted)]">
                          <span>Entry <span className="font-mono text-[var(--text)]">{formatPrice(trade.entry_price)}</span></span>
                          {trade.exit_price ? (
                            <span>Exit <span className="font-mono text-[var(--text)]">{formatPrice(trade.exit_price)}</span></span>
                          ) : null}
                          <span>x{trade.leverage} · ROI <span className={`font-mono ${pnlColor(trade.pnl_percent)}`}>{formatNumber(trade.pnl_percent)}%</span></span>
                          {trade.close_reason ? <span className="col-span-2">{trade.close_reason}</span> : null}
                        </div>

                        {trade.setup_tags.length > 0 ? (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {trade.setup_tags.slice(0, 4).map((tag) => (
                              <span key={tag} className="rounded bg-[var(--surface-raised)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
                                {tag}
                              </span>
                            ))}
                          </div>
                        ) : null}

                        {(trade.replay_payload?.reasons?.length ?? 0) > 0 ? (
                          <details className="mt-2">
                            <summary className="cursor-pointer select-none text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)] hover:text-[var(--text)]">
                              Why this trade?
                            </summary>
                            <ul className="mt-1 space-y-0.5 pl-2">
                              {trade.replay_payload.reasons!.map((reason, i) => (
                                <li key={i} className="text-[11px] text-[var(--muted)] before:mr-1 before:content-['·']">
                                  {reason}
                                </li>
                              ))}
                            </ul>
                          </details>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
