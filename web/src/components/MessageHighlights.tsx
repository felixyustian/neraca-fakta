import { useI18n } from "../i18n";
import { STATUS } from "../status";
import type { Verdict } from "../types";

interface Props {
  title?: string;
  message: string;
  verdicts: Verdict[];
  active: number | null;
  onHover: (i: number | null) => void;
}

interface Span {
  start: number;
  end: number;
  index: number;
}

/** Locate each claim's source text in the message; drop overlaps (first claim wins). */
function locate(message: string, verdicts: Verdict[]): Span[] {
  const lower = message.toLowerCase();
  const spans: Span[] = [];
  verdicts.forEach((v, index) => {
    const needle = v.claim.source_text.trim();
    if (!needle) return;
    let start = message.indexOf(needle);
    if (start < 0) start = lower.indexOf(needle.toLowerCase());
    if (start < 0) return;
    const end = start + needle.length;
    if (spans.some((s) => start < s.end && end > s.start)) return;
    spans.push({ start, end, index });
  });
  return spans.sort((a, b) => a.start - b.start);
}

export default function MessageHighlights({ title, message, verdicts, active, onHover }: Props) {
  const { t, verdict } = useI18n();
  const spans = locate(message, verdicts);
  const parts: React.ReactNode[] = [];
  let pos = 0;
  for (const s of spans) {
    if (s.start > pos) parts.push(message.slice(pos, s.start));
    const v = verdicts[s.index];
    const st = STATUS[v.label];
    parts.push(
      <mark
        key={s.index}
        className={`hl st-${st.key} ${active === s.index ? "active" : ""}`}
        title={verdict(v.label)}
        tabIndex={0}
        onPointerEnter={() => onHover(s.index)}
        onPointerLeave={() => onHover(null)}
        onFocus={() => onHover(s.index)}
        onBlur={() => onHover(null)}
        onClick={() => document.getElementById(`verdict-${s.index}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
      >
        <span className="hl-icon" aria-hidden>{st.icon}</span>
        {message.slice(s.start, s.end)}
      </mark>,
    );
    pos = s.end;
  }
  if (pos < message.length) parts.push(message.slice(pos));

  return (
    <section className="card message-card" aria-label={title ?? t("originalMessage")}>
      <div className="section-head">
        <h3>{title ?? t("originalMessage")}</h3>
        <span className="muted small">{t("originalHint")}</span>
      </div>
      <p className="message-text">{parts}</p>
    </section>
  );
}
