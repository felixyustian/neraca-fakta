import { useCountUp } from "../hooks";
import { useI18n } from "../i18n";
import { scoreStatus } from "../status";

/** Accuracy score as a meter ring; fill color carries the status, number carries the value. */
export default function ScoreRing({ score }: { score: number | null }) {
  const { t } = useI18n();
  const shown = useCountUp(score);
  const r = 52;
  const c = 2 * Math.PI * r;
  const frac = (shown ?? 0) / 100;
  return (
    <div className="score-ring" title={t("scoreHelp")}>
      <svg viewBox="0 0 128 128" width="128" height="128" role="img" aria-label={`${t("scoreLabel")}: ${score ?? "—"}`}>
        <circle className={`ring-track s-${scoreStatus(score)}`} cx="64" cy="64" r={r} />
        <circle
          className={`ring-fill s-${scoreStatus(score)}`}
          cx="64"
          cy="64"
          r={r}
          strokeDasharray={`${c * frac} ${c}`}
          transform="rotate(-90 64 64)"
        />
      </svg>
      <div className="ring-center">
        <span className="ring-value">{shown === null ? "—" : Math.round(shown)}</span>
        {score !== null && <span className="ring-unit">/100</span>}
      </div>
    </div>
  );
}
