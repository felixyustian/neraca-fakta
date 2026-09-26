import type { Lang } from "./types";

const LOCALE: Record<Lang, string> = { id: "id-ID", en: "en-US" };

export function num(x: number, lang: Lang, digits = 1): string {
  return x.toLocaleString(LOCALE[lang], { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

const IDR_UNITS: Record<Lang, [number, string][]> = {
  id: [[1e12, "T"], [1e9, "M"], [1e6, "jt"]],
  en: [[1e12, "T"], [1e9, "B"], [1e6, "M"]],
};

/** Rp238,74 T (id) / Rp238.74 T (en). */
export function idr(x: number, lang: Lang, digits = 2): string {
  const sign = x < 0 ? "-" : "";
  const a = Math.abs(x);
  for (const [div, unit] of IDR_UNITS[lang]) {
    if (a >= div) return `${sign}Rp${num(a / div, lang, digits)} ${unit}`;
  }
  return `${sign}Rp${a.toLocaleString(LOCALE[lang], { maximumFractionDigits: 0 })}`;
}

/** Axis ticks: shortest clean form, e.g. "150 T", "-20 T". */
export function idrTick(x: number, lang: Lang): string {
  if (x === 0) return "0";
  for (const [div, unit] of IDR_UNITS[lang]) {
    if (Math.abs(x) >= div) return `${(x / div).toLocaleString(LOCALE[lang], { maximumFractionDigits: 1 })} ${unit}`;
  }
  return x.toLocaleString(LOCALE[lang]);
}

export function pct(x: number, lang: Lang, signed = false, digits = 1): string {
  return `${signed && x > 0 ? "+" : ""}${num(x, lang, digits)}%`;
}

export function price(x: number, lang: Lang): string {
  return `Rp${x.toLocaleString(LOCALE[lang], { maximumFractionDigits: 0 })}`;
}

export function value(x: number | null, unit: "pct" | "idr" | "none", lang: Lang, signed = false): string {
  if (x === null) return "—";
  if (unit === "idr") return idr(x, lang);
  if (unit === "pct") return pct(x, lang, signed);
  return num(x, lang);
}

export function date(iso: string | null, lang: Lang, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString(LOCALE[lang], {
    day: "numeric",
    month: "short",
    year: "numeric",
    ...opts,
  });
}

export function quarterLabel(iso: string | null): string {
  if (!iso) return "—";
  const m = Number(iso.slice(5, 7));
  return `Q${Math.floor((m - 1) / 3) + 1} ${iso.slice(0, 4)}`;
}

/** Evenly spaced "nice" ticks covering [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min];
  const span = max - min;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step; // always cover max, even when it's tiny next to min
  const ticks: number[] = [];
  for (let v = start; v <= end + step * 1e-6; v += step) ticks.push(Number(v.toPrecision(12)));
  return ticks;
}
