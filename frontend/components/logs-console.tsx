"use client";

import { useEffect, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { BotLog } from "@/lib/types";

export function LogsConsole() {
  const [logs, setLogs] = useState<BotLog[]>([]);
  const [filter, setFilter] = useState<"ALL" | BotLog["level"]>("ALL");
  const [categoryFilter, setCategoryFilter] = useState<"ALL" | BotLog["category"]>("TRADE");
  const [hasMore, setHasMore] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const PAGE_SIZE = 200;

  // "YYYY-MM-DD" -> ISO instant at local midnight (end = start of the next day).
  function dayBoundary(value: string, addDays = 0) {
    if (!value) return undefined;
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d + addDays).toISOString();
  }

  function query(extra: { before_id?: number } = {}) {
    return {
      category: categoryFilter,
      level: filter,
      limit: PAGE_SIZE,
      from: dayBoundary(dateFrom),
      to: dayBoundary(dateTo, 1),
      ...extra,
    };
  }

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    api.logs(query()).then((rows) => {
      setLogs(rows);
      setHasMore(rows.length === PAGE_SIZE);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter, filter, dateFrom, dateTo]);

  async function loadMore() {
    const last = logs[logs.length - 1];
    if (!last) return;
    const rows = await api.logs(query({ before_id: last.id }));
    setLogs((current) => [...current, ...rows]);
    setHasMore(rows.length === PAGE_SIZE);
  }

  const visible = logs;
  return (
    <PageFrame title="Bot logs" description="Market decisions, safety blocks, execution events, and errors.">
      <Panel className="min-w-0">
        <PanelHeader
          title="Event history"
          action={
            <div className="flex flex-wrap items-center gap-2">
              <input type="date" aria-label="From date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} className="h-8 rounded-md border border-[var(--line-strong)] bg-[var(--background)] px-2 text-xs outline-none" />
              <span className="text-xs text-[var(--muted)]">to</span>
              <input type="date" aria-label="To date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} className="h-8 rounded-md border border-[var(--line-strong)] bg-[var(--background)] px-2 text-xs outline-none" />
              {(dateFrom || dateTo) && (
                <button onClick={() => { setDateFrom(""); setDateTo(""); }} className="h-8 px-2 text-xs text-[var(--muted)] hover:text-[var(--foreground)]">Clear</button>
              )}
              <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value as typeof categoryFilter)} className="h-8 rounded-md border border-[var(--line-strong)] bg-[var(--background)] px-2 text-xs outline-none">
                <option value="ALL">All events</option>
                <option value="TRADE">Trade only</option>
                <option value="SCANNER">Scanner only</option>
                <option value="SYSTEM">System only</option>
              </select>
              <select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} className="h-8 rounded-md border border-[var(--line-strong)] bg-[var(--background)] px-2 text-xs outline-none">
                <option>ALL</option><option>INFO</option><option>WARNING</option><option>ERROR</option>
              </select>
            </div>
          }
        />
        {visible.length ? (
          <div className="divide-y divide-[var(--line)]">
            {visible.map((log) => (
              <article key={log.id} className="grid gap-2 px-4 py-3 md:grid-cols-[100px_110px_1fr_170px] md:items-center">
                <span className={`font-mono text-[10px] font-bold ${log.level === "ERROR" ? "text-[var(--negative)]" : log.level === "WARNING" ? "text-[var(--warning)]" : "text-[var(--positive)]"}`}>{log.level}</span>
                <span className="font-mono text-xs">{log.symbol}</span>
                <p className="text-sm">{log.message}</p>
                <time className="text-xs text-[var(--muted)] md:text-right">{new Date(log.created_at).toLocaleString()}</time>
              </article>
            ))}
            {hasMore && (
              <button onClick={loadMore} className="w-full px-4 py-3 text-xs text-[var(--muted)] hover:text-[var(--foreground)]">
                Load older events
              </button>
            )}
          </div>
        ) : (
          <div className="grid min-h-64 place-items-center text-sm text-[var(--muted)]">No matching bot events.</div>
        )}
      </Panel>
    </PageFrame>
  );
}

