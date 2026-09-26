import { useI18n, type StringKey } from "../i18n";
import type { Platform, SourceInfo } from "../types";

const PLATFORM: Record<Platform, string> = {
  web: "Web",
  youtube: "YouTube",
  tiktok: "TikTok",
  instagram: "Instagram",
  threads: "Threads",
  facebook: "Facebook",
  x: "X",
};

const STATUS: Record<SourceInfo["status"], { key: StringKey; cls: string; icon: string }> = {
  ok: { key: "srcOk", cls: "st-ok", icon: "✓" },
  partial: { key: "srcPartial", cls: "st-partial", icon: "≈" },
  blocked: { key: "srcBlocked", cls: "st-unknown", icon: "🔒" },
  error: { key: "srcError", cls: "st-bad", icon: "!" },
};

/** "author · host · N characters", skipping repeats (a site's author is often its own domain). */
function metaLine(s: SourceInfo, host: string, chars: string): string {
  const title = s.title || host;
  const parts = [s.author, host, s.chars ? chars : null].filter((x): x is string => !!x && x !== title);
  return [...new Set(parts)].join(" · ");
}

export default function SourcesCard({ sources }: { sources: SourceInfo[] }) {
  const { t, tx, lang } = useI18n();
  return (
    <section className="card sources-card" aria-label={t("sourcesTitle")}>
      <div className="section-head">
        <h3>{t("sourcesTitle")}</h3>
      </div>
      <ul className="sources">
        {sources.map((s) => {
          const st = STATUS[s.status];
          let host = s.url;
          try {
            host = new URL(s.url).hostname.replace(/^www\./, "");
          } catch {
            /* keep the raw URL */
          }
          return (
            <li key={s.url}>
              <span className={`plat plat-${s.platform}`}>{PLATFORM[s.platform]}</span>
              <div className="src-body">
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="src-title">
                  {s.title || host}
                </a>
                <span className="muted small">
                  {metaLine(s, host, t("srcChars", { n: s.chars.toLocaleString(lang === "id" ? "id-ID" : "en-US") }))}
                </span>
                {s.analyzed_video && <span className="chip-static video-chip">▶ {t("videoAnalyzed")}</span>}
                {s.note && s.status !== "ok" && !s.analyzed_video && (
                  <span className="src-note small">{tx(s.note)}</span>
                )}
              </div>
              <span className={`pill ${st.cls}`}>
                <span className="pill-icon" aria-hidden>
                  {st.icon}
                </span>
                {t(st.key)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
