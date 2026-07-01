"use client";

import { useEffect, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { BotLog } from "@/lib/types";

export function LogsConsole() {
  const [logs, setLogs] = useState<BotLog[]>([]);
  const [filter, setFilter] = useState<"ALL" | BotLog["level"]>("ALL");

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    api.logs().then(setLogs);
  }, []);

  const visible = filter === "ALL" ? logs : logs.filter((log) => log.level === filter);
  return (
    <PageFrame title="Bot logs" description="Market decisions, safety blocks, execution events, and errors.">
      <Panel className="min-w-0">
        <PanelHeader
          title="Event history"
          action={
            <select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} className="h-8 rounded-md border border-[var(--line-strong)] bg-[var(--background)] px-2 text-xs outline-none">
              <option>ALL</option><option>INFO</option><option>WARNING</option><option>ERROR</option>
            </select>
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
          </div>
        ) : (
          <div className="grid min-h-64 place-items-center text-sm text-[var(--muted)]">No matching bot events.</div>
        )}
      </Panel>
    </PageFrame>
  );
}

