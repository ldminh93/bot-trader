"use client";

import { useEffect, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { api, getToken } from "@/lib/api";
import type { UserPerformanceEntry } from "@/lib/types";
import { formatNumber, pnlColor } from "@/lib/utils";

type SortField = "total_profit" | "win_rate" | "username";
type SortDirection = "asc" | "desc";

function toOrdering(field: SortField, direction: SortDirection): string {
  return direction === "desc" ? `-${field}` : field;
}

export function UsersConsole() {
  const [users, setUsers] = useState<UserPerformanceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);
  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState<SortField>("total_profit");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    api
      .me()
      .then((currentUser) => {
        if (!currentUser.is_staff) {
          window.location.href = "/dashboard";
        }
      })
      .catch(() => {
        window.location.href = "/dashboard";
      });
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .userPerformance({ ordering: toOrdering(sortField, sortDirection), search: search || undefined })
      .then((result) => {
        setUsers(result.results);
        setLoading(false);
      })
      .catch(() => {
        setAccessDenied(true);
        setLoading(false);
      });
  }, [sortField, sortDirection, search]);

  function toggleSort(field: SortField) {
    if (field === sortField) {
      setSortDirection((direction) => (direction === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  }

  function sortIndicator(field: SortField) {
    if (field !== sortField) return "";
    return sortDirection === "desc" ? " ↓" : " ↑";
  }

  if (accessDenied) {
    return (
      <PageFrame title="Users" description="Win rate and profit across every registered user.">
        <Panel className="grid min-h-40 place-items-center px-6 text-center text-sm text-[var(--muted)]">
          You don&apos;t have permission to view this page.
        </Panel>
      </PageFrame>
    );
  }

  return (
    <PageFrame title="Users" description="Win rate and profit across every registered user.">
      <Panel>
        <PanelHeader
          title="All users"
          action={
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search username or email"
              className="w-full rounded-[var(--radius)] border border-[var(--line)] bg-[var(--background)] px-2 py-1 text-xs text-[var(--text)] focus:outline-none sm:w-64"
            />
          }
        />
        {loading ? (
          <div className="grid min-h-40 place-items-center px-6 text-center text-sm text-[var(--muted)]">
            Loading…
          </div>
        ) : !users.length ? (
          <div className="grid min-h-40 place-items-center px-6 text-center">
            <div>
              <p className="font-semibold">No users found</p>
              <p className="mt-1 text-sm text-[var(--muted)]">Try clearing the search filter.</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead className="text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">
                <tr className="border-b border-[var(--line)]">
                  <th className="px-4 py-3">
                    <button type="button" onClick={() => toggleSort("username")} className="hover:text-[var(--text)]">
                      User{sortIndicator("username")}
                    </button>
                  </th>
                  <th className="px-3 py-3">Trades</th>
                  <th className="px-3 py-3">
                    <button type="button" onClick={() => toggleSort("win_rate")} className="hover:text-[var(--text)]">
                      Win rate{sortIndicator("win_rate")}
                    </button>
                  </th>
                  <th className="px-3 py-3">
                    <button
                      type="button"
                      onClick={() => toggleSort("total_profit")}
                      className="hover:text-[var(--text)]"
                    >
                      Total profit{sortIndicator("total_profit")}
                    </button>
                  </th>
                  <th className="px-4 py-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--surface-raised)]">
                    <td className="px-4 py-3">
                      <div className="font-semibold">{user.username}</div>
                      <div className="text-[10px] text-[var(--muted)]">{user.email}</div>
                    </td>
                    <td className="px-3 py-3 font-mono">{user.total_trades}</td>
                    <td className="px-3 py-3 font-mono">
                      {user.win_rate === null ? (
                        <span className="text-[var(--muted)]">No trades yet</span>
                      ) : (
                        `${formatNumber(user.win_rate)}%`
                      )}
                    </td>
                    <td className={`px-3 py-3 font-mono font-semibold ${pnlColor(user.total_profit)}`}>
                      {formatNumber(user.total_profit)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {user.is_active ? (
                        <span className="text-[var(--muted)]">Active</span>
                      ) : (
                        <span className="rounded px-1.5 py-0.5 text-[10px] font-bold bg-[var(--negative)]/15 text-[var(--negative)]">
                          Deactivated
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </PageFrame>
  );
}
