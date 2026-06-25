import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";

export function PageFrame({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <AppShell>
      <header className="flex min-h-20 items-center justify-between border-b border-[var(--line)] px-4 py-4 md:px-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">{description}</p>
        </div>
        {action}
      </header>
      <div className="p-4 md:p-6">{children}</div>
    </AppShell>
  );
}

