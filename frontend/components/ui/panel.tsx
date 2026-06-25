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
        "flex min-h-11 items-center justify-between border-b border-[var(--line)] px-4",
        className,
      )}
    >
      <h2 className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--muted)]">{title}</h2>
      {action}
    </div>
  );
}

