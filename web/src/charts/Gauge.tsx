import { value as fmtValue } from "../format";
import { useWidth } from "../hooks";
import { useI18n } from "../i18n";
import { STATUS, signedStated } from "../status";
import type { Verdict } from "../types";

const H = 64;
const PAD = 14;

/**
 * Claim vs data on one scale: the "partial" band, the "match" band inside it, the actual
 * value as an ink tick, and the claim as a status-colored dot. Shows at a glance how far off
 * a claim is and which zone it landed in.
 */
export default function Gauge({ v }: { v: Verdict }) {
  const { lang, t } = useI18n();
  const [ref, width] = useWidth<HTMLDivElement>(420);
  const stated = signedStated(v);
  const actual = v.actual_value;
  if (actual === null || !v.ok_range || !v.partial_range) return null;

  const unit = v.actual_unit;
  const vals = [actual, ...v.partial_range, ...v.ok_range, ...(stated !== null ? [stated] : [])];
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.12;
  lo -= pad;
  hi += pad;
  const x = (n: number) => PAD + ((n - lo) / (hi - lo)) * (width - PAD * 2);
  const trackY = 30;
  const status = STATUS[v.label].key;
  const fmt = (n: number) => fmtValue(n, unit, lang, unit === "pct" && (v.claim.claim_type !== "dividend_yield"));
  const claimLeft = stated !== null && x(stated) < x(actual);
  // Keep labels inside the svg: pin to the edge they're near, else center / push away.
  const edge = (px: number, fallback: "start" | "middle" | "end") =>
    px < 70 ? "start" : px > width - 70 ? "end" : fallback;

  return (
    <div className="gauge" ref={ref}>
      <svg width={width} height={H} role="img" aria-label={`${t("claim")} ${stated !== null ? fmt(stated) : "—"}, ${t("data")} ${fmt(actual)}`}>
        <rect className="g-track" x={PAD} y={trackY - 5} width={width - PAD * 2} height={10} rx={5} />
        <rect className="g-partial" x={x(v.partial_range[0])} y={trackY - 5} width={Math.max(2, x(v.partial_range[1]) - x(v.partial_range[0]))} height={10} rx={5} />
        <rect className="g-ok" x={x(v.ok_range[0])} y={trackY - 5} width={Math.max(2, x(v.ok_range[1]) - x(v.ok_range[0]))} height={10} rx={5} />
        {lo < 0 && hi > 0 && unit === "pct" && <line className="g-zero" x1={x(0)} x2={x(0)} y1={trackY - 9} y2={trackY + 9} />}
        <line className="g-actual" x1={x(actual)} x2={x(actual)} y1={trackY - 11} y2={trackY + 11} />
        <text className="g-label" x={x(actual)} y={trackY + 26} textAnchor={edge(x(actual), stated === null ? "middle" : claimLeft ? "start" : "end")}>
          {t("data")} {fmt(actual)}
        </text>
        {stated !== null && (
          <>
            <circle className={`g-claim s-${status}`} cx={x(stated)} cy={trackY} r={6.5} />
            <text className="g-label strong" x={x(stated)} y={trackY - 14} textAnchor={edge(x(stated), "middle")}>
              {t("claim")} {fmt(stated)}
            </text>
          </>
        )}
      </svg>
      <ul className="gauge-legend">
        <li><span className="swatch g-ok-sw" aria-hidden />{t("okZone")}</li>
        <li><span className="swatch g-partial-sw" aria-hidden />{t("partialZone")}</li>
      </ul>
    </div>
  );
}
