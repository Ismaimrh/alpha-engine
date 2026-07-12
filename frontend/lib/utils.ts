import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

export const fmtPct = (v: number | null, dp = 1) =>
  v === null ? "n/a" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(dp)}%`;

export const pnlColor = (v: number | null) =>
  v === null ? "text-muted" : v >= 0 ? "text-gain" : "text-loss";
