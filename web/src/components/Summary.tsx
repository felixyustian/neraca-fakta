import { useState } from "react";
import ScoreRing from "../charts/ScoreRing";
import { useI18n } from "../i18n";
import { LABEL_ORDER, STATUS, accuracyScore, scoreStatus } from "../status";
import type { CheckResult, VerdictLabel } from "../types";

interface Props {
  result: CheckResult;
  filter: VerdictLabel | null;
  onFilter: (f: VerdictLabel | null) => void;
}

export default function Summary({ result, filter, onFilter }: Props) {
  const { t, tx, verdict, claimType } = useI18n();
  const [copied, setCopied] = useState(false);
  const total = result.verdicts.length;
  const score = accuracyScore(result.verdicts);
  const counts = LABEL_ORDER.map((l) => [l, result.verdicts.filter((v) => v.label === l).length] as const);
  const status = scoreStatus(score);
  const headline =
    total === 0
      ? t("noClaims")
      : score === null
        ? t("headlineNone")
        : status === "ok"
          ? t("headlineGood")
          : status === "partial"
            ? t("headlineMixed")
            : t("headlineBad");

  async function copy() {
    const lines = [
      `${t("docTitle")}: ${total === 1 ? t("oneClaimChecked") : t("claimsChecked", { n: total })}` +
        (score !== null ? ` · ${t("scoreLabel")} ${score}/100` : ""),
      "",
      ...result.verdicts.map(
        (v) => `${STATUS[v.label].icon} ${v.claim.ticker} · ${claimType(v.claim.claim_type)}: ${verdict(v.label)}. ${tx(v.reason)}`,
      ),
      "",
      t("summaryDisclaimer"),
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }

  return (
    <section className="card summary-card">
      <ScoreRing score={score} />
      <div className="summary-body">
        <span className="eyebrow">{total === 1 ? t("oneClaimChecked") : t("claimsChecked", { n: total })}</span>
        <h2>{headline}</h2>
        {total > 0 && (
          <>
            <div className="bar" role="img" aria-label={counts.map(([l, n]) => `${verdict(l)}: ${n}`).join(", ")}>
              {counts.map(([l, n]) => (n ? <span key={l} className={`seg st-${STATUS[l].key}`} style={{ flexGrow: n }} /> : null))}
            </div>
            <div className="filters" role="group" aria-label={t("filterHint")}>
              <button type="button" className={`filter ${filter === null ? "on" : ""}`} onClick={() => onFilter(null)}>
                {t("filterAll")} <strong>{total}</strong>
              </button>
              {counts.map(([l, n]) => (
                <button
                  key={l}
                  type="button"
                  disabled={!n}
                  aria-pressed={filter === l}
                  className={`filter ${filter === l ? "on" : ""}`}
                  onClick={() => onFilter(filter === l ? null : l)}
                >
                  <span className={`dot st-${STATUS[l].key}`} aria-hidden>{STATUS[l].icon}</span>
                  {verdict(l)} <strong>{n}</strong>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      {total > 0 && (
        <button type="button" className="ghost copy-btn" onClick={copy}>
          {copied ? `✓ ${t("copied")}` : `⧉ ${t("copySummary")}`}
        </button>
      )}
    </section>
  );
}
