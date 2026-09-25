"use client";

import {
  CalendarBlank,
  ChartBar,
  ChartLineUp,
  Coins,
  GearSix,
  ListBullets,
  Pulse,
  SignOut,
  SquaresFour,
  TrendUp,
  Users,
} from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { clearSession } from "@/lib/api";
import { useCurrentUser } from "@/lib/current-user-context";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/dashboard", label: "Overview", icon: SquaresFour },
  { href: "/trades", label: "Trades", icon: ChartLineUp },
  { href: "/top-movers", label: "Top Movers", icon: TrendUp },
  { href: "/scanned", label: "Scanned", icon: Coins },
  { href: "/calendar", label: "Calendar", icon: CalendarBlank },
  { href: "/analytics", label: "Analytics", icon: ChartBar },
  { href: "/logs", label: "Logs", icon: ListBullets },
  { href: "/settings", label: "Settings", icon: GearSix },
];

const adminNavigation = [{ href: "/users", label: "Users", icon: Users }];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isStaff } = useCurrentUser();
  const [usernameParam, setUsernameParam] = useState("");

  // Carries the currently-viewed user (e.g. from /users/[id]/calendar) into
  // the Trades/Calendar nav links so staff don't get bounced back to their
  // own data while browsing someone else's.
  const viewedUserMatch = pathname.match(/^\/users\/(\d+)\/(?:calendar|trades)/);
  const viewedUserId = viewedUserMatch?.[1];

  useEffect(() => {
    setUsernameParam(new URLSearchParams(window.location.search).get("username") ?? "");
  }, [pathname]);

  const visibleNavigation = (isStaff ? [...navigation, ...adminNavigation] : navigation).map((item) => {
    if (viewedUserId && (item.href === "/trades" || item.href === "/calendar")) {
      const suffix = item.href.slice(1);
      const query = usernameParam ? `?username=${encodeURIComponent(usernameParam)}` : "";
      return { ...item, href: `/users/${viewedUserId}/${suffix}${query}` };
    }
    return item;
  });

  function signOut() {
    clearSession();
    router.push("/login");
  }

  return (
    <div className="min-h-[100dvh] bg-[var(--background)] lg:grid lg:grid-cols-[220px_1fr]">
      <aside className="fixed inset-x-0 bottom-0 z-20 border-t border-[var(--line)] bg-[var(--surface)]/96 shadow-[0_-12px_36px_rgba(0,0,0,0.28)] backdrop-blur lg:inset-y-0 lg:left-0 lg:right-auto lg:flex lg:w-[220px] lg:flex-col lg:border-r lg:border-t-0 lg:bg-[var(--surface)] lg:shadow-none">
        <div className="hidden h-16 items-center gap-3 border-b border-[var(--line)] px-5 lg:flex">
          <div className="grid size-8 place-items-center rounded-[var(--radius)] bg-[var(--accent)] text-[var(--accent-ink)]">
            <Pulse size={19} weight="bold" />
          </div>
          <div>
            <p className="text-sm font-bold tracking-tight">Futures Operator</p>
            <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">Paper-first system</p>
          </div>
        </div>
        <nav
          className={cn(
            "grid gap-1 px-2 py-2 [padding-bottom:calc(env(safe-area-inset-bottom)+0.5rem)] lg:flex lg:flex-1 lg:flex-col lg:gap-1 lg:p-3",
            isStaff ? "grid-cols-9" : "grid-cols-8",
          )}
        >
          {visibleNavigation.map((item) => {
            const active = pathname === item.href.split("?")[0];
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex min-h-[3.5rem] flex-col items-center justify-center gap-1 rounded-[calc(var(--radius)-4px)] px-1 text-[10px] font-semibold text-[var(--muted)] transition-colors lg:h-10 lg:min-h-0 lg:flex-row lg:justify-start lg:gap-3 lg:rounded-[var(--radius)] lg:px-3 lg:text-sm",
                  active && "bg-[var(--surface-raised)] text-[var(--text)]",
                )}
              >
                <item.icon size={19} weight={active ? "fill" : "regular"} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <button
          onClick={signOut}
          className="m-3 hidden h-10 items-center gap-3 rounded-[var(--radius)] px-3 text-sm text-[var(--muted)] hover:bg-[var(--surface-raised)] hover:text-[var(--text)] lg:flex"
        >
          <SignOut size={19} />
          Sign out
        </button>
      </aside>
      <main className="min-w-0 pb-[calc(env(safe-area-inset-bottom)+5.5rem)] lg:col-start-2 lg:pb-0">{children}</main>
    </div>
  );
}
