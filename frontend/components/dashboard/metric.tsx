export function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0 px-3 py-3 sm:px-4">
      <p className="text-[9px] font-semibold uppercase tracking-[0.1em] leading-[1.35] text-[var(--muted)] sm:text-[10px]">{label}</p>
      <p className={`mt-1 break-words font-mono text-[15px] font-semibold leading-tight sm:text-sm ${tone ?? ""}`}>{value}</p>
      {detail && <p className="mt-1 text-[10px] leading-4 text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

export function EmptyChart({ label = "No market series yet. Start the bot to collect data." }: { label?: string }) {
  return <div className="grid h-full place-items-center text-center text-xs text-[var(--muted)]">{label}</div>;
}
