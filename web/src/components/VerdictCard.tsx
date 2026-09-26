import { useState } from "react";
import Gauge from "../charts/Gauge";
import { value } from "../format";
import { useI18n } from "../i18n";
import { STATUS, signedStated } from "../status";
import type { Verdict } from "../types";

interface Props {
  v: Verdict;
  index: number;
  active: boolean;
  onHover: (i: number | null) => void;
}

export default function VerdictCard({ v, index, active, onHover }: Props) {
  const { lang, t, tx, verdict, claimType } = useI18n();
  const [open, setOpen] = useState(false);
  const s = STATUS[v.label];
  const c = v.claim;
  const growth = c.claim_type === "revenue_growth" || c.claim_type === "profit_growth";
  const stated = signedStated(v);
  const hasNumbers = c.claim_type !== "unverifiable" && (stated !== null || v.actual_value !== null);

  const tolerance =
    c.claim_type === "unverifiable"
      ? t("tolUnverifiable")
      : growth
        ? t("tolGrowth")
        : c.claim_type === "dividend_yield"
          ? t("tolYield")
          : t("tolAmount", { p: c.claim_type === "market_cap" ? 15 : 20 });

  return (
    <li
      id={`verdict-${index}`}
      className={`verdict card st-${s.key} ${active ? "active" : ""}`}
      onPointerEnter={() => onHover(index)}
      onPointerLeave={() => onHover(null)}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="verdict-head">
        <span className={`pill st-${s.key}`}>
          <span className="pill-icon" aria-hidden>{s.icon}</span>
          {verdict(v.label)}
        </span>
        <span className="claim-type">
          <strong>{c.ticker}</strong> · {claimType(c.claim_type)}
        </span>
      </div>

      <blockquote>“{c.source_text}”</blockquote>

      {hasNumbers && (
        <div className="compare">
          <div className="num-block">
            <span className="num-label">{t("claim")}</span>
            <span className="num-big">{value(stated, c.unit, lang, growth)}</span>
          </div>
          <span className="arrow" aria-hidden>→</span>
          <div className="num-block">
            <span className="num-label">{t("data")}</span>
            <span className="num-big">{value(v.actual_value, v.actual_unit, lang, growth)}</span>
          </div>
        </div>
      )}

      {v.ok_range && <Gauge v={v} />}

      <p className="reason">{tx(v.reason)}</p>

      <div className="verdict-foot">
        {v.period_compared && (
          <span className="chip-static">
            {t("period")}: {tx(v.period_compared)}
          </span>
        )}
        <button type="button" className="link-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {t("howComputed")} {open ? "▴" : "▾"}
        </button>
      </div>
      {open && <p className="how muted small">{tolerance}</p>}
    </li>
  );
}
