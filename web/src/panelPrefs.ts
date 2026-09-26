// Which market panels a viewer sees, where, and with which items. Per-viewer convenience:
// kept in localStorage, and the page works the same if storage is unavailable.

export type SectionId =
  | "ihsg"
  | "watchlist"
  | "indices"
  | "marketCap"
  | "commodities"
  | "forex"
  | "movers"
  | "mostTraded"
  | "news";

export type Side = "left" | "right";

export interface PanelPrefs {
  layout: { id: SectionId; side: Side; visible: boolean }[]; // array order = display order
  ticker: boolean;
  indices: string[] | null; // null = defaults
  currencies: string[] | null;
  commodities: string[] | null;
  newsCount: number;
  watchlist: string[];
}

export const DEFAULT_INDICES = ["LQ45", "IDX30", "KOMPAS100", "IDXHIDIV20", "JII70", "IDXBUMN20"];
export const DEFAULT_CURRENCIES = ["USD", "SGD", "EUR", "JPY", "CNY", "AUD"];
export const NEWS_COUNTS = [3, 5, 8, 12];
export const WATCHLIST_MAX = 5;

export const DEFAULT_PREFS: PanelPrefs = {
  layout: [
    { id: "ihsg", side: "left", visible: true },
    { id: "watchlist", side: "left", visible: true },
    { id: "indices", side: "left", visible: true },
    { id: "marketCap", side: "left", visible: true },
    { id: "commodities", side: "left", visible: true },
    { id: "forex", side: "left", visible: true },
    { id: "movers", side: "right", visible: true },
    { id: "mostTraded", side: "right", visible: true },
    { id: "news", side: "right", visible: true },
  ],
  ticker: true,
  indices: null,
  currencies: null,
  commodities: null,
  newsCount: 8,
  watchlist: [],
};

const KEY = "cekfakta.panels";

/** Merge stored prefs with defaults so new sections appear and unknown ones are dropped. */
function normalize(raw: Partial<PanelPrefs>): PanelPrefs {
  const known = new Set(DEFAULT_PREFS.layout.map((s) => s.id));
  const stored = (raw.layout ?? []).filter((s) => known.has(s.id) && (s.side === "left" || s.side === "right"));
  const seen = new Set(stored.map((s) => s.id));
  return {
    ...DEFAULT_PREFS,
    ...raw,
    layout: [...stored, ...DEFAULT_PREFS.layout.filter((s) => !seen.has(s.id))],
    newsCount: NEWS_COUNTS.includes(raw.newsCount ?? 0) ? raw.newsCount! : DEFAULT_PREFS.newsCount,
    watchlist: (raw.watchlist ?? []).filter((s) => /^[A-Z]{4}$/.test(s)).slice(0, WATCHLIST_MAX),
  };
}

export function loadPanelPrefs(): PanelPrefs {
  try {
    const s = localStorage.getItem(KEY);
    return s ? normalize(JSON.parse(s)) : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePanelPrefs(p: PanelPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* private mode: applies for this visit only */
  }
}

/** Move a section up/down among the sections on the same side. */
export function moveSection(p: PanelPrefs, id: SectionId, dir: -1 | 1): PanelPrefs {
  const layout = [...p.layout];
  const i = layout.findIndex((s) => s.id === id);
  let j = i + dir;
  while (j >= 0 && j < layout.length && layout[j].side !== layout[i].side) j += dir;
  if (j < 0 || j >= layout.length) return p;
  [layout[i], layout[j]] = [layout[j], layout[i]];
  return { ...p, layout };
}
