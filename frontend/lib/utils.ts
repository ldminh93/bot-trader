import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number | string | null | undefined, digits = 2) {
  const parsed = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(parsed);
}

export function formatCompact(value: number | string | null | undefined) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(Number(value ?? 0));
}

export function pnlColor(value: number | string) {
  const parsed = Number(value);
  if (parsed > 0) return "text-[var(--positive)]";
  if (parsed < 0) return "text-[var(--negative)]";
  return "text-[var(--muted)]";
}

