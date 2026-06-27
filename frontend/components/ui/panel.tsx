import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        "rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)]",
        className,
      )}
      {...props}
    />
  );
}

export function PanelHeader({
  title,
  action,
  className,
}: {
  title: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-11 flex-col items-start gap-2 border-b border-[var(--line)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <h2 className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--muted)]">{title}</h2>
      {action ? <div className="w-full min-w-0 sm:w-auto">{action}</div> : null}
    </div>
  );
}
