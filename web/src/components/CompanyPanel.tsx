import { useState } from "react";
import BarChart from "../charts/BarChart";
import PriceChart from "../charts/PriceChart";
import { date, idr, idrTick, num, pct, price, quarterLabel } from "../format";
import { useCountUp } from "../hooks";
import { useI18n } from "../i18n";
import type { CompanySnapshot } from "../types";

type Tab = "price" | "fin" | "div";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "up" | "down" }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className={`stat-value ${tone ?? ""}`}>{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

/** Animated number in a stat tile. */
function useAnimated(v: number | null) {
  return useCountUp(v, 800);
}

export default function CompanyPanel({ c }: { c: CompanySnapshot }) {
  const { lang, t } = useI18n();
  const [tab, setTab] = useState<Tab>(c.prices.length > 1 ? "price" : "fin");
  const [table, setTable] = useState(false);

  const cap = useAnimated(c.market_cap);
  const rev = useAnimated(c.yoy_revenue_growth_pct);
  const earn = useAnimated(c.yoy_earnings_growth_pct);
  const yld = useAnimated(c.dividend_yield_pct);
  const px = useAnimated(c.last_close_price);
  const tone = (v: number | null) => (v === null ? undefined : v >= 0 ? "up" : "down");

  const tabs: { id: Tab; label: string }[] = [
    { id: "price", label: t("tabPrice") },
    { id: "fin", label: t("tabFinancials") },
    { id: "div", label: t("tabDividends") },
  ];

  return (
    <article className="company card">
      <header className="company-head">
        <div className="company-id">
          <span className="ticker-badge">{c.ticker}</span>
          <div>
            <h3>{c.name ?? c.ticker}</h3>
            <span className="muted small">{[c.sector, c.sub_sector].filter(Boolean).join(" · ")}</span>
          </div>
        </div>
        {c.last_close_price !== null && (
          <div className="company-price">
            <span className="price-now">{price(px ?? 0, lang)}</span>
            <span className="muted small">
              {c.daily_change_pct !== null && (
                <span className={`delta ${tone(c.daily_change_pct)}`}>
                  {c.daily_change_pct > 0 ? "▲" : c.daily_change_pct < 0 ? "▼" : "•"} {t("change", { v: pct(c.daily_change_pct, lang, true, 2) })}
                </span>
              )}{" "}
              · {date(c.latest_close_date, lang)}
            </span>
          </div>
        )}
      </header>

      <div className="stats">
        <Stat
          label={t("marketCap")}
          value={cap === null ? "—" : idr(cap, lang)}
          sub={c.market_cap_rank ? t("rank", { n: c.market_cap_rank }) : undefined}
        />
        <Stat
          label={t("yoyRevenue")}
          value={rev === null ? "—" : pct(rev, lang, true)}
          sub={t("latestQuarter", { q: quarterLabel(c.latest_quarter) })}
          tone={tone(c.yoy_revenue_growth_pct)}
        />
        <Stat
          label={t("yoyEarnings")}
          value={earn === null ? "—" : pct(earn, lang, true)}
          sub={t("latestQuarter", { q: quarterLabel(c.latest_quarter) })}
          tone={tone(c.yoy_earnings_growth_pct)}
        />
        <Stat label={t("dividendYield")} value={yld === null ? t("noDividend") : pct(yld, lang, false, 2)} sub={t("ttm")} />
      </div>

      <div className="tabs-row">
        <div className="tabs" role="tablist">
          {tabs.map((x) => (
            <button
              key={x.id}
              role="tab"
              type="button"
              aria-selected={tab === x.id}
              className={tab === x.id ? "tab active" : "tab"}
              onClick={() => setTab(x.id)}
            >
              {x.label}
            </button>
          ))}
        </div>
        <button type="button" className="link-btn" onClick={() => setTable((v) => !v)} aria-pressed={table}>
          {table ? t("showChart") : t("showTable")}
        </button>
      </div>

      <div className="tab-body" role="tabpanel">
        {tab === "price" && <PriceTab c={c} table={table} />}
        {tab === "fin" && <FinTab c={c} table={table} />}
        {tab === "div" && <DivTab c={c} table={table} />}
      </div>
    </article>
  );
}

function PriceTab({ c, table }: { c: CompanySnapshot; table: boolean }) {
  const { lang, t } = useI18n();
  if (c.prices.length < 2) return <p className="muted">{t("noPrices")}</p>;
  const first = c.prices[0].date;
  const last = c.prices[c.prices.length - 1].date;
  return (
    <>
      <p className="chart-title">{t("priceChartTitle", { from: date(first, lang), to: date(last, lang) })}</p>
      {table ? (
        <DataTable
          head={[t("dateCol"), t("close")]}
          rows={[...c.prices].reverse().map((p) => [date(p.date, lang), price(p.close, lang)])}
        />
      ) : (
        <PriceChart points={c.prices} />
      )}
      {c.low_52w && c.high_52w && c.last_close_price !== null && (
        <RangeBar lo={c.low_52w.price} hi={c.high_52w.price} now={c.last_close_price} />
      )}
      {c.all_time_high && (
        <p className="muted small">
          {t("ath", { p: price(c.all_time_high.price, lang), d: date(c.all_time_high.date, lang) })}
        </p>
      )}
    </>
  );
}

/** Where today's price sits in its 52-week range. */
function RangeBar({ lo, hi, now }: { lo: number; hi: number; now: number }) {
  const { lang, t } = useI18n();
  const frac = hi > lo ? Math.min(1, Math.max(0, (now - lo) / (hi - lo))) : 0.5;
  return (
    <div className="range">
      <div className="range-head">
        <span className="small strong">{t("range52")}</span>
      </div>
      <div className="range-track" aria-label={`${t("range52")}: ${price(lo, lang)} – ${price(hi, lang)}`}>
        <div className="range-fill" style={{ width: `${frac * 100}%` }} />
        <div className="range-dot" style={{ left: `${frac * 100}%` }} />
      </div>
      <div className="range-ends small">
        <span>{t("low")} {price(lo, lang)}</span>
        <span>{t("high")} {price(hi, lang)}</span>
      </div>
    </div>
  );
}

function FinTab({ c, table }: { c: CompanySnapshot; table: boolean }) {
  const { lang, t } = useI18n();
  if (!c.annual.length) return <p className="muted">{t("noFinancials")}</p>;
  return (
    <>
      <p className="chart-title">{t("finChartTitle")}</p>
      {table ? (
        <DataTable
          head={[t("yearCol"), t("revenue"), t("earnings")]}
          rows={c.annual.map((a) => [
            String(a.year),
            a.revenue === null ? "—" : idr(a.revenue, lang),
            a.earnings === null ? "—" : idr(a.earnings, lang),
          ])}
        />
      ) : (
        <BarChart
          series={[
            { label: t("revenue"), color: "var(--series-1)" },
            { label: t("earnings"), color: "var(--series-2)" },
          ]}
          rows={c.annual.map((a) => ({ category: String(a.year), values: [a.revenue, a.earnings] }))}
          format={(v) => idr(v, lang)}
          tick={(v) => idrTick(v, lang)}
          ariaLabel={t("finChartTitle")}
        />
      )}
    </>
  );
}

function DivTab({ c, table }: { c: CompanySnapshot; table: boolean }) {
  const { lang, t } = useI18n();
  const rows = c.dividends.filter((d) => d.yield_pct !== null);
  if (!rows.length) return <p className="muted">{t("noDividends")}</p>;
  return (
    <>
      <p className="chart-title">{t("divChartTitle")}</p>
      {table ? (
        <DataTable
          head={[t("yearCol"), t("yieldCol"), t("dpsCol")]}
          rows={rows.map((d) => [
            String(d.year),
            pct(d.yield_pct!, lang, false, 2),
            d.total === null ? "—" : `Rp${num(d.total, lang, 1)}`,
          ])}
        />
      ) : (
        <BarChart
          series={[{ label: t("yieldCol"), color: "var(--series-1)" }]}
          rows={rows.map((d) => ({
            category: String(d.year),
            values: [d.yield_pct],
            extra: d.total === null ? undefined : `${t("dpsCol")}: Rp${num(d.total, lang, 1)}`,
          }))}
          format={(v) => pct(v, lang, false, 2)}
          tick={(v) => pct(v, lang, false, v % 1 ? 1 : 0)}
          ariaLabel={t("divChartTitle")}
        />
      )}
    </>
  );
}

function DataTable({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>{head.map((h) => <th key={h}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
