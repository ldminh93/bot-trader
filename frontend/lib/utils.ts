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

/**
 * Format a price/quantity-like value with enough decimal places to stay
 * distinguishable for sub-$1 assets (e.g. a 0.0001-priced coin needs 8
 * decimals, not 2-4, or entry/stop/TP all round to the same displayed value).
 */
export function formatPrice(value: number | string | null | undefined) {
  const parsed = Number(value ?? 0);
  const abs = Math.abs(parsed);
  let digits = 2;
  if (abs > 0 && abs < 1) {
    digits = Math.min(8, Math.max(4, 4 - Math.floor(Math.log10(abs))));
  }
  return formatNumber(parsed, digits);
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

