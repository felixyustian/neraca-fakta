import type { Verdict, VerdictLabel } from "./types";

export type StatusKey = "ok" | "partial" | "bad" | "unknown";

export const STATUS: Record<VerdictLabel, { key: StatusKey; icon: string }> = {
  "Sesuai data": { key: "ok", icon: "✓" },
  "Sebagian sesuai": { key: "partial", icon: "≈" },
  "Tidak sesuai": { key: "bad", icon: "✕" },
  "Tidak dapat diverifikasi": { key: "unknown", icon: "?" },
};

export const LABEL_ORDER: VerdictLabel[] = ["Sesuai data", "Sebagian sesuai", "Tidak sesuai", "Tidak dapat diverifikasi"];

/** 0–100: matches count 1, partial 0.5, over checkable claims. null if nothing was checkable. */
export function accuracyScore(verdicts: Verdict[]): number | null {
  const checkable = verdicts.filter((v) => v.label !== "Tidak dapat diverifikasi");
  if (!checkable.length) return null;
  const pts = checkable.reduce((s, v) => s + (v.label === "Sesuai data" ? 1 : v.label === "Sebagian sesuai" ? 0.5 : 0), 0);
  return Math.round((pts / checkable.length) * 100);
}

export function scoreStatus(score: number | null): StatusKey {
  if (score === null) return "unknown";
  return score >= 70 ? "ok" : score >= 40 ? "partial" : "bad";
}

/** Claimed value with its sign applied ("turun 15%" -> -15). */
export function signedStated(v: Verdict): number | null {
  const c = v.claim;
  if (c.stated_value === null) return null;
  const growth = c.claim_type === "revenue_growth" || c.claim_type === "profit_growth";
  return growth && c.direction === "down" ? -c.stated_value : c.stated_value;
}
