import { useState } from "react";
import Sparkline from "../charts/Sparkline";
import { date as fmtDate, idr, num, pct, price } from "../format";
import { useI18n, type StringKey } from "../i18n";
import { DEFAULT_CURRENCIES, DEFAULT_INDICES, type PanelPrefs, type SectionId, type Side } from "../panelPrefs";
import type { Lang, MarketSnapshot, WatchQuote } from "../types";

const LOCALE: Record<Lang, string> = { id: "id-ID", en: "en-US" };

export const SECTION_LABEL: Record<SectionId, StringKey> = {
  ihsg: "secIhsg",
  watchlist: "watchlistTitle",
  indices: "indicesTitle",
  marketCap: "idxMarketCap",
  commodities: "commoditiesTitle",
  forex: "forexTitle",
  movers: "moversTitle",
  mostTraded: "mostTraded",
  news: "newsTitle",
};

function Delta({ v, digits = 2 }: { v: number | null; digits?: number }) {
  const { lang } = useI18n();
  if (v === null) return <span className="delta-pill flat">—</span>;
  const dir = v >= 0.005 ? "up" : v <= -0.005 ? "down" : "flat";
  return (
    <span className={`delta-pill ${dir}`}>
      <span aria-hidden>{dir === "up" ? "▲" : dir === "down" ? "▼" : "•"}</span>
      {pct(Math.abs(v), lang, false, digits)}
    </span>
  );
}

function Unavailable({ reason }: { reason?: string }) {
  const { t } = useI18n();
  const key: StringKey =
    reason === "budget" ? "unavailBudget" : reason === "offline" ? "unavailOffline" : "unavailError";
  return <p className="panel-empty">{t(key)}</p>;
}

function PanelCard({
  title,
  children,
  foot,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  foot?: string;
  className?: string;
}) {
  return (
    <section className={`panel-card ${className}`}>
      <h3 className="panel-title">{title}</h3>
      {children}
      {foot && <p className="panel-foot">{foot}</p>}
    </section>
  );
}

/** Newsroom-style date: time for today's items, day + month otherwise. Timestamps come without a zone. */
function newsTime(ts: string, lang: Lang): string {
  if (!ts) return "";
  const [d, t] = ts.split("T");
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return d === today && t ? t.slice(0, 5) : fmtDate(d, lang, { year: undefined });
}

function num2(v: number, lang: Lang, digits = 2) {
  return v.toLocaleString(LOCALE[lang], { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// ---------------------------------------------------------------------------------

export function NewsTicker({ market }: { market: MarketSnapshot | null }) {
  const { t, lang } = useI18n();
  const items = market?.news.slice(0, 10) ?? [];
  if (!items.length) return null;
  // Track rendered twice so the loop is seamless.
  const track = [...items, ...items];
  return (
    <div className="ticker" role="region" aria-label={t("newsTickerLabel")}>
      <span className="ticker-label">
        <span className="live-dot" aria-hidden /> {t("latest")}
      </span>
      <div className="ticker-viewport">
        <ul className="ticker-track" style={{ animationDuration: `${items.length * 9}s` }}>
          {track.map((n, i) => (
            <li key={i} aria-hidden={i >= items.length || undefined}>
              <a href={n.url} target="_blank" rel="noopener noreferrer" tabIndex={i >= items.length ? -1 : 0}>
                <time>{newsTime(n.timestamp, lang)}</time>
                {n.symbols[0] && <span className="ticker-sym">{n.symbols[0]}</span>}
                <span className="ticker-title">{n.title}</span>
                <span className="ticker-src">{n.source}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// --- sections ----------------------------------------------------------------------

interface SectionProps {
  market: MarketSnapshot;
  prefs: PanelPrefs;
  watch: WatchQuote[] | null;
  onCustomize: () => void;
}

function IhsgSection({ market }: SectionProps) {
  const { t, lang } = useI18n();
  return (
    <section className="panel-card hero-index">
      {market.ihsg ? (
        <>
          <span className="panel-title">{t("ihsgName")}</span>
          <div className="hero-index-row">
            <span className="hero-index-value">{num2(market.ihsg.value, lang)}</span>
            <Delta v={market.ihsg.change_pct} />
          </div>
          <Sparkline
            points={market.ihsg_series}
            format={(v) => num2(v, lang)}
            formatDate={(d) => fmtDate(d, lang)}
            label="IHSG"
          />
        </>
      ) : (
        <Unavailable reason={market.unavailable.indices} />
      )}
    </section>
  );
}

function WatchlistSection({ prefs, watch, onCustomize }: SectionProps) {
  const { t, lang } = useI18n();
  if (!prefs.watchlist.length) {
    return (
      <PanelCard title={t("watchlistTitle")}>
        <p className="panel-empty">{t("watchlistEmpty")}</p>
        <button type="button" className="link-btn" onClick={onCustomize}>
          + {t("watchlistAdd")}
        </button>
      </PanelCard>
    );
  }
  return (
    <PanelCard title={t("watchlistTitle")}>
      {watch === null ? (
        <p className="panel-empty">…</p>
      ) : (
        <ul className="rows watch">
          {watch.map((w) => (
            <li key={w.symbol}>
              <span className="row-sym">{w.symbol}</span>
              {w.unavailable ? (
                <span className="row-sub inline">
                  {t(
                    w.unavailable === "not_found"
                      ? "watchNotFound"
                      : w.unavailable === "budget"
                        ? "unavailBudget"
                        : w.unavailable === "offline"
                          ? "watchOffline"
                          : "unavailError",
                  )}
                </span>
              ) : (
                <>
                  <span className="watch-spark">
                    {w.series.length > 1 && <MiniLine points={w.series.map((p) => p.value)} />}
                  </span>
                  <span className="row-val">{w.close !== null ? price(w.close, lang) : "—"}</span>
                  <Delta v={w.change_pct} />
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </PanelCard>
  );
}

/** Tiny inline trend for list rows (no axes, no hover: the row shows the numbers). */
function MiniLine({ points }: { points: number[] }) {
  const w = 56,
    h = 18;
  const lo = Math.min(...points),
    hi = Math.max(...points);
  const d = points
    .map(
      (v, i) =>
        `${i ? "L" : "M"}${((i / (points.length - 1)) * w).toFixed(1)},${(h - 2 - ((v - lo) / (hi - lo || 1)) * (h - 4)).toFixed(1)}`,
    )
    .join("");
  return (
    <svg width={w} height={h} aria-hidden className="mini-line">
      <path d={d} />
    </svg>
  );
}

function IndicesSection({ market, prefs }: SectionProps) {
  const { t, lang } = useI18n();
  const wanted = prefs.indices ?? DEFAULT_INDICES;
  const rows = wanted.map((c) => market.indices.find((q) => q.code === c)).filter((q) => q !== undefined);
  return (
    <PanelCard title={t("indicesTitle")}>
      {rows.length ? (
        <ul className="rows">
          {rows.map((q) => (
            <li key={q.code}>
              <span className="row-sym">{q.code}</span>
              <span className="row-val">{num2(q.value, lang)}</span>
              <Delta v={q.change_pct} />
            </li>
          ))}
        </ul>
      ) : market.indices.length ? (
        <p className="panel-empty">{t("nothingSelected")}</p>
      ) : (
        <Unavailable reason={market.unavailable.indices} />
      )}
    </PanelCard>
  );
}

function MarketCapSection({ market }: SectionProps) {
  const { t, lang } = useI18n();
  return (
    <PanelCard title={t("idxMarketCap")}>
      {market.market_cap ? (
        <>
          <div className="hero-index-row">
            <span className="stat-like">{idr(market.market_cap.value, lang)}</span>
            <Delta v={market.market_cap.change_pct} />
          </div>
          <Sparkline
            points={market.market_cap_series}
            height={40}
            format={(v) => idr(v, lang)}
            formatDate={(d) => fmtDate(d, lang)}
            label={t("idxMarketCap")}
          />
        </>
      ) : (
        <Unavailable reason={market.unavailable.market_cap} />
      )}
    </PanelCard>
  );
}

function CommoditiesSection({ market, prefs }: SectionProps) {
  const { t, lang } = useI18n();
  const rows = market.commodities.filter((c) => !prefs.commodities || prefs.commodities.includes(c.name));
  return (
    <PanelCard title={t("commoditiesTitle")}>
      {rows.length ? (
        <ul className="rows">
          {rows.map((c) => (
            <li key={c.name} title={fmtDate(c.date, lang)}>
              <span className="row-sym">{c.name}</span>
              <span className="row-val">
                {num(c.price, lang, 0)} <span className="unit">{c.unit}</span>
              </span>
              <Delta v={c.change_pct} digits={1} />
              <span className="row-sub">{fmtDate(c.date, lang, { day: undefined })}</span>
            </li>
          ))}
        </ul>
      ) : market.commodities.length ? (
        <p className="panel-empty">{t("nothingSelected")}</p>
      ) : (
        <Unavailable reason={market.unavailable.commodities} />
      )}
    </PanelCard>
  );
}

function ForexSection({ market, prefs }: SectionProps) {
  const { t, lang } = useI18n();
  const wanted = prefs.currencies ?? DEFAULT_CURRENCIES;
  const rows = wanted.map((c) => market.forex.find((f) => f.currency === c)).filter((f) => f !== undefined);
  return (
    <PanelCard
      title={t("forexTitle")}
      foot={market.forex[0] ? t("forexSource", { d: fmtDate(market.forex[0].date, lang) }) : undefined}
    >
      {rows.length ? (
        <ul className="rows">
          {rows.map((f) => (
            <li key={f.currency}>
              <span className="row-sym">
                {f.currency}
                <span className="fx-quote">/IDR</span>
              </span>
              <span className="row-val">{num2(f.rate, lang, f.rate < 1000 ? 2 : 0)}</span>
              <Delta v={f.change_pct} />
            </li>
          ))}
        </ul>
      ) : market.forex.length ? (
        <p className="panel-empty">{t("nothingSelected")}</p>
      ) : (
        <Unavailable reason={market.unavailable.forex} />
      )}
    </PanelCard>
  );
}

function MoversSection({ market }: SectionProps) {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<"gainers" | "losers">("gainers");
  const movers = tab === "gainers" ? market.gainers : market.losers;
  const maxMove = Math.max(1, ...movers.map((m) => Math.abs(m.change_pct)));
  return (
    <PanelCard
      title={t("moversTitle")}
      foot={market.movers_date ? t("sectorsSource", { d: fmtDate(market.movers_date, lang) }) : undefined}
    >
      <div className="mini-tabs" role="tablist">
        {(["gainers", "losers"] as const).map((k) => (
          <button
            key={k}
            role="tab"
            type="button"
            aria-selected={tab === k}
            className={tab === k ? "on" : ""}
            onClick={() => setTab(k)}
          >
            {t(k)}
          </button>
        ))}
      </div>
      {movers.length ? (
        <ul className="rows movers">
          {movers.map((m) => (
            <li key={m.symbol} title={m.name ?? undefined}>
              <span className="row-sym">{m.symbol}</span>
              <span className="mover-bar" aria-hidden>
                <span
                  className={m.change_pct >= 0 ? "up" : "down"}
                  style={{ width: `${(Math.abs(m.change_pct) / maxMove) * 100}%` }}
                />
              </span>
              <span className="row-val">{m.price !== null ? price(m.price, lang) : ""}</span>
              <Delta v={m.change_pct} />
            </li>
          ))}
        </ul>
      ) : (
        <Unavailable reason={market.unavailable.movers} />
      )}
    </PanelCard>
  );
}

function MostTradedSection({ market }: SectionProps) {
  const { t, lang } = useI18n();
  const compact = new Intl.NumberFormat(LOCALE[lang], { notation: "compact", maximumFractionDigits: 1 });
  return (
    <PanelCard
      title={t("mostTraded")}
      foot={market.most_traded_date ? t("sectorsSource", { d: fmtDate(market.most_traded_date, lang) }) : undefined}
    >
      {market.most_traded.length ? (
        <ul className="rows">
          {market.most_traded.map((m, i) => (
            <li key={m.symbol} title={m.name ?? undefined}>
              <span className="rank">{i + 1}</span>
              <span className="row-sym">{m.symbol}</span>
              <span className="row-val">
                {compact.format(m.volume)} <span className="unit">{t("shares")}</span>
              </span>
              <span className="row-sub">{m.price !== null ? price(m.price, lang) : ""}</span>
            </li>
          ))}
        </ul>
      ) : (
        <Unavailable reason={market.unavailable.most_traded} />
      )}
    </PanelCard>
  );
}

function NewsSection({ market, prefs }: SectionProps) {
  const { t, lang } = useI18n();
  return (
    <PanelCard title={t("newsTitle")} foot={t("newsNote")}>
      {market.news.length ? (
        <ul className="news-list">
          {market.news.slice(0, prefs.newsCount).map((n) => (
            <li key={n.url}>
              <a href={n.url} target="_blank" rel="noopener noreferrer">
                <span className="news-title">{n.title}</span>
                <span className="news-meta">
                  <time>{newsTime(n.timestamp, lang)}</time> · {n.source}
                  {n.symbols.map((s) => (
                    <span key={s} className="sym-chip">
                      {s}
                    </span>
                  ))}
                </span>
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <Unavailable reason={market.unavailable.news} />
      )}
    </PanelCard>
  );
}

const SECTIONS: Record<SectionId, (p: SectionProps) => React.ReactElement> = {
  ihsg: IhsgSection,
  watchlist: WatchlistSection,
  indices: IndicesSection,
  marketCap: MarketCapSection,
  commodities: CommoditiesSection,
  forex: ForexSection,
  movers: MoversSection,
  mostTraded: MostTradedSection,
  news: NewsSection,
};

// --- a side column -----------------------------------------------------------------

interface SidePanelProps {
  side: Side;
  market: MarketSnapshot | null;
  off: boolean;
  prefs: PanelPrefs;
  watch: WatchQuote[] | null;
  onCustomize: () => void;
}

export function SidePanel({ side, market, off, prefs, watch, onCustomize }: SidePanelProps) {
  const { t, lang } = useI18n();
  const cls = `side side-${side}`;
  const title = t(side === "left" ? "markets" : "highlights");
  const head = (
    <div className="side-head">
      <h2>{title}</h2>
      <span className="side-head-actions">
        {side === "left" && market?.data_source === "fixtures" && (
          <span className="snap-badge">{t("offlineSnapshot")}</span>
        )}
        {!off && (
          <button
            type="button"
            className="icon-btn customize-btn"
            onClick={onCustomize}
            title={t("customizePanels")}
            aria-label={t("customizePanels")}
          >
            ⚙
          </button>
        )}
      </span>
    </div>
  );
  if (off)
    return (
      <aside className={cls}>
        {head}
        <p className="panel-empty">{t("panelsOff")}</p>
      </aside>
    );
  if (!market)
    return (
      <aside className={cls} aria-busy="true">
        {head}
        <div className="panel-skeleton" />
      </aside>
    );

  const sections = prefs.layout.filter((s) => s.side === side && s.visible);
  const asOf = market.ihsg?.date ?? market.market_cap?.date;
  const showsSectors = sections.some((s) => ["ihsg", "indices", "marketCap"].includes(s.id));
  return (
    <aside className={cls} aria-label={title}>
      {head}
      {sections.length === 0 && (
        <p className="panel-empty">
          {t("sideEmpty")}{" "}
          <button type="button" className="link-btn" onClick={onCustomize}>
            {t("customizePanels")}
          </button>
        </p>
      )}
      {sections.map((s) => {
        const Section = SECTIONS[s.id];
        return <Section key={s.id} market={market} prefs={prefs} watch={watch} onCustomize={onCustomize} />;
      })}
      {showsSectors && asOf && <p className="panel-foot">{t("sectorsSource", { d: fmtDate(asOf, lang) })}</p>}
    </aside>
  );
}
