import { useEffect, useMemo, useRef, useState } from "react";
import { checkMessage, checkWithMedia, getHealth, getMarket, getWatchlist } from "./api";
import Attachments, { acceptFiles } from "./components/Attachments";
import SourcesCard from "./components/SourcesCard";
import CompanyPanel from "./components/CompanyPanel";
import { NewsTicker, SidePanel } from "./components/MarketPanels";
import PanelSettings from "./components/PanelSettings";
import { loadPanelPrefs, savePanelPrefs, type PanelPrefs } from "./panelPrefs";
import MessageHighlights from "./components/MessageHighlights";
import Summary from "./components/Summary";
import VerdictCard from "./components/VerdictCard";
import { useStoredState } from "./hooks";
import { I18nContext, makeI18n, useI18n, type StringKey } from "./i18n";
import SettingsDialog, { providerName } from "./SettingsDialog";
import { clearSettings, EMPTY_SETTINGS, loadSettings, saveSettings, type LLMSettings } from "./settings";
import type { CheckResult, Health, Lang, MarketSnapshot, VerdictLabel, WatchQuote } from "./types";

const MARKET_POLL_MS = 10 * 60 * 1000; // server caches; polling only picks up refreshed data

// Examples use tickers present in the offline fixtures, so they work without an API key.
// The messages stay in Indonesian in both UI languages: that is what real tips look like.
const EXAMPLES: { key: StringKey; text: string }[] = [
  {
    key: "exHype",
    text: "🔥 INFO A1 🔥 $GOTO laba Q2 2026 naik 200% YoY! Pendapatan tumbuh 30%. Target 100 minggu depan, pasti ARA! Buruan sebelum terbang 🚀",
  },
  {
    key: "exDividend",
    text: "TLKM dividen yield 12%, market cap Rp 240 T. Laba bersih kuartal ini Rp 6,3 triliun. Wajib koleksi!",
  },
  {
    key: "exWrong",
    text: "BBCA laba turun 15% yoy, pendapatan naik 1,5% QoQ. Mending jual dulu sebelum longsor.",
  },
];

type Theme = "system" | "light" | "dark";

export default function App() {
  const [lang, setLang] = useStoredState<Lang>("cekfakta.lang", "id", ["id", "en"]);
  const [theme, setTheme] = useStoredState<Theme>("cekfakta.theme", "system", ["system", "light", "dark"]);
  const i18n = useMemo(() => makeI18n(lang), [lang]);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = i18n.t("docTitle");
  }, [lang, i18n]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
  }, [theme]);

  return (
    <I18nContext.Provider value={i18n}>
      <Page lang={lang} setLang={setLang} theme={theme} setTheme={setTheme} />
    </I18nContext.Provider>
  );
}

interface PageProps {
  lang: Lang;
  setLang: (l: Lang) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
}

function Page({ lang, setLang, theme, setTheme }: PageProps) {
  const { t, tx } = useI18n();
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<"attachTooMany" | "attachBadType" | null>(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [llm, setLlm] = useState<LLMSettings>(loadSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [filter, setFilter] = useState<VerdictLabel | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [market, setMarket] = useState<MarketSnapshot | null>(null);
  const [marketOff, setMarketOff] = useState(false);
  const [panelPrefs, setPanelPrefs] = useState<PanelPrefs>(loadPanelPrefs);
  const [panelsOpen, setPanelsOpen] = useState(false);
  const [watch, setWatch] = useState<WatchQuote[] | null>(null);
  const watchKey = panelPrefs.watchlist.join(",");

  // Watchlist: refetch when the symbols change, and on the market polling interval.
  useEffect(() => {
    if (!watchKey) return setWatch([]);
    let alive = true;
    const load = () =>
      getWatchlist(watchKey.split(","))
        .then((w) => alive && setWatch(w))
        .catch(() => alive && setWatch([]));
    setWatch(null);
    load();
    const id = setInterval(load, MARKET_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [watchKey]);

  const updatePanels = (p: PanelPrefs) => {
    setPanelPrefs(p);
    savePanelPrefs(p);
  };
  const resultsRef = useRef<HTMLDivElement>(null);
  const mastheadRef = useRef<HTMLDivElement>(null);

  // Sticky side panels sit just under the masthead, whose height changes with the ticker and wrapping.
  useEffect(() => {
    const el = mastheadRef.current;
    if (!el) return;
    // Set on our own container: extensions sometimes rewrite <html style>.
    const apply = () =>
      el.parentElement?.style.setProperty("--masthead-h", `${Math.ceil(el.getBoundingClientRect().height)}px`);
    apply(); // right away: ResizeObserver doesn't fire in windows the browser isn't painting
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [market, panelPrefs.ticker]); // re-measure when the ticker appears or is toggled

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    const load = () =>
      getMarket()
        .then((m) => {
          setMarket(m);
          setMarketOff(m === null);
        })
        .catch(() => {});
    load();
    const id = setInterval(load, MARKET_POLL_MS);
    return () => clearInterval(id);
  }, []);

  function addFiles(incoming: File[]) {
    const [next, err] = acceptFiles(files, incoming);
    setFiles(next);
    setFileError(err);
  }

  async function run(text = message, attached = files) {
    if ((!text.trim() && !attached.length) || loading) return;
    setLoading(true);
    setError(null);
    try {
      const r = attached.length ? await checkWithMedia(text, attached, llm) : await checkMessage(text, llm);
      setResult(r);
      setFilter(null);
      getHealth()
        .then(setHealth)
        .catch(() => {});
      requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("genericError"));
    } finally {
      setLoading(false);
    }
  }

  const aiName = providerName(llm.provider || health?.llm_default || "rules", t("noAI"));
  const nextTheme: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
  const themeIcon = { system: "◐", light: "☀", dark: "☾" }[theme];
  const themeLabel = { system: t("themeSystem"), light: t("themeLight"), dark: t("themeDark") }[theme];

  return (
    <div className="app">
      <div className="masthead" ref={mastheadRef}>
        <header className="topbar">
          <div className="topbar-inner">
            <a className="brand" href="#top" aria-label={t("docTitle")}>
              <span className="logo" aria-hidden>
                <svg viewBox="0 0 24 24" width="18" height="18">
                  <path
                    d="M5 12.5l4.2 4.2L19 7"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <span className="brand-name">{t("appName")}</span>
            </a>
            <div className="top-actions">
              <StatusBadge health={health} />
              <div className="seg-toggle" role="group" aria-label={t("language")}>
                {(["id", "en"] as Lang[]).map((l) => (
                  <button
                    key={l}
                    type="button"
                    aria-pressed={lang === l}
                    className={lang === l ? "on" : ""}
                    onClick={() => setLang(l)}
                  >
                    {l.toUpperCase()}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="icon-btn round"
                title={themeLabel}
                aria-label={themeLabel}
                onClick={() => setTheme(nextTheme[theme])}
              >
                {themeIcon}
              </button>
              <button type="button" className="ghost ai-btn" onClick={() => setSettingsOpen(true)} disabled={!health}>
                <span aria-hidden>⚙</span> AI: {aiName}
              </button>
            </div>
          </div>
        </header>
        {panelPrefs.ticker && <NewsTicker market={market} />}
      </div>

      <PanelSettings
        open={panelsOpen}
        prefs={panelPrefs}
        market={market}
        onChange={updatePanels}
        onClose={() => setPanelsOpen(false)}
      />

      <SettingsDialog
        open={settingsOpen}
        health={health}
        settings={llm}
        onSave={(s) => {
          setLlm(s);
          saveSettings(s);
          setSettingsOpen(false);
        }}
        onClear={() => {
          setLlm(EMPTY_SETTINGS);
          clearSettings();
        }}
        onClose={() => setSettingsOpen(false)}
      />

      <div className="shell">
        <main className="page" id="top">
          <section className="hero">
            <span className="slogan">
              <span className="slogan-dot" aria-hidden /> {t("slogan")}
            </span>
            <h1>{t("heroTitle")}</h1>
            <p className="hero-sub">{t("heroSub")}</p>
            <ol className="steps">
              {(
                [
                  ["step1", "step1Sub", "M4 5h16v10H8l-4 4z"],
                  ["step2", "step2Sub", "M4 6h16M4 12h10M4 18h7"],
                  ["step3", "step3Sub", "M4 19V9M10 19V5M16 19v-7M22 19H2"],
                ] as [StringKey, StringKey, string][]
              ).map(([title, sub, d], i) => (
                <li key={title}>
                  <span className="step-icon" aria-hidden>
                    <svg viewBox="0 0 24 24" width="20" height="20">
                      <path
                        d={d}
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                  <span>
                    <span className="step-n">{i + 1}</span> <strong>{t(title)}</strong>
                    <span className="muted small block">{t(sub)}</span>
                  </span>
                </li>
              ))}
            </ol>
            {(health?.bots?.telegram || health?.bots?.whatsapp) && (
              <div className="chat-links">
                <span className="muted small">{t("chatVia")}</span>
                {health.bots.telegram && (
                  <a
                    className="chat-btn tg"
                    href={`https://t.me/${health.bots.telegram}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
                      <path
                        d="M21 4 3 11l6 2 2 6 3-4 5 4z"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinejoin="round"
                      />
                    </svg>
                    {t("viaTelegram")}
                  </a>
                )}
                {health.bots.whatsapp && (
                  <a
                    className="chat-btn wa"
                    href={`https://wa.me/${health.bots.whatsapp}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
                      <path
                        d="M4 20l1.3-4A8 8 0 1 1 8 18.7z"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinejoin="round"
                      />
                    </svg>
                    {t("viaWhatsApp")}
                  </a>
                )}
              </div>
            )}
          </section>

          <section
            className={`card input-card ${dragging ? "dragging" : ""}`}
            aria-label={t("inputLabel")}
            onDragOver={(e) => {
              if ([...e.dataTransfer.items].some((i) => i.kind === "file")) {
                e.preventDefault();
                setDragging(true);
              }
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles([...e.dataTransfer.files]);
            }}
          >
            {dragging && <div className="drop-overlay">{t("dropHere")}</div>}
            <label htmlFor="msg" className="field-label">
              {t("inputLabel")}
            </label>
            <textarea
              id="msg"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onPaste={(e) => {
                const images = [...e.clipboardData.files].filter((f) => f.type.startsWith("image/"));
                if (images.length) {
                  e.preventDefault();
                  addFiles(images);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
              }}
              placeholder={t("placeholder")}
              rows={5}
              maxLength={4000}
            />
            <div className="input-meta muted small">
              <span>{t("chars", { n: message.length })}</span>
              <span>{t("shortcut")}</span>
            </div>
            <p className="sources-hint muted small">{t("sourcesHint")}</p>
            {health?.demo && (
              <p className="demo-notice small">
                <span aria-hidden>ⓘ</span> {t("demoNotice", { list: health.offline_tickers?.join(", ") || "—" })}
              </p>
            )}
            <Attachments
              files={files}
              onChange={setFiles}
              onError={setFileError}
              needsAI={(llm.provider || health?.llm_default || "rules") === "rules"}
            />
            {fileError && <p className="hint warn">{t(fileError)}</p>}
            <div className="examples-label muted small">{t("tryExample")}</div>
            <div className="examples">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.key}
                  type="button"
                  className="example"
                  onClick={() => {
                    setMessage(ex.text);
                    run(ex.text);
                  }}
                >
                  <strong>{t(ex.key)}</strong>
                  <span className="example-text">{ex.text}</span>
                </button>
              ))}
            </div>
            <div className="input-actions">
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <button
                type="button"
                className="primary big"
                onClick={() => run()}
                disabled={loading || (!message.trim() && !files.length)}
              >
                {loading ? (
                  <>
                    <span className="spinner" aria-hidden /> {t("checking")}
                  </>
                ) : (
                  t("check")
                )}
              </button>
            </div>
          </section>

          {result && (
            <div ref={resultsRef} className={`results ${loading ? "refreshing" : ""}`} aria-live="polite">
              <Summary result={result} filter={filter} onFilter={setFilter} />

              {result.sources.length > 0 && <SourcesCard sources={result.sources} />}

              {result.verdicts.length > 0 && result.message.trim() && (
                <MessageHighlights
                  message={result.message}
                  verdicts={result.verdicts}
                  active={active}
                  onHover={setActive}
                />
              )}

              {result.media_text && (
                <MessageHighlights
                  title={t("mediaText")}
                  message={result.media_text}
                  verdicts={result.verdicts}
                  active={active}
                  onHover={setActive}
                />
              )}

              {result.verdicts.length > 0 && (
                <section>
                  <h2 className="section-title">{t("claimsTitle")}</h2>
                  <ol className="verdicts">
                    {result.verdicts.map((v, i) =>
                      filter && v.label !== filter ? null : (
                        <VerdictCard
                          key={`${result.message}-${i}`}
                          v={v}
                          index={i}
                          active={active === i}
                          onHover={setActive}
                        />
                      ),
                    )}
                  </ol>
                </section>
              )}

              {result.notes.length > 0 && (
                <ul className="notes">
                  {result.notes.map((n, i) => (
                    <li key={i}>{tx(n)}</li>
                  ))}
                </ul>
              )}

              {result.companies.length > 0 && (
                <section>
                  <h2 className="section-title">{t("companyTitle")}</h2>
                  <div className="companies">
                    {result.companies.map((c) => (
                      <CompanyPanel key={c.ticker} c={c} />
                    ))}
                  </div>
                </section>
              )}

              <p className="meta muted small">
                {t("meta", {
                  x:
                    result.extractor === "rules"
                      ? t("rulesName")
                      : `${providerName(result.extractor, t("noAI"))} (${result.model})`,
                  d: result.data_source === "live" ? t("sourceLive") : t("sourceOffline"),
                  c: result.credits_spent,
                })}
              </p>
            </div>
          )}
        </main>
        <SidePanel
          side="left"
          market={market}
          off={marketOff}
          prefs={panelPrefs}
          watch={watch}
          onCustomize={() => setPanelsOpen(true)}
        />
        <SidePanel
          side="right"
          market={market}
          off={marketOff}
          prefs={panelPrefs}
          watch={watch}
          onCustomize={() => setPanelsOpen(true)}
        />
      </div>

      <footer className="foot muted small">{t("footer")}</footer>
    </div>
  );
}

function StatusBadge({ health }: { health: Health | null }) {
  const { t } = useI18n();
  if (!health) return <span className="badge badge-off">{t("apiOffline")}</span>;
  const live = health.data_source === "live";
  const title = live
    ? t("credits", { spent: health.credits_spent ?? 0, cap: health.credit_cap ?? 0 })
    : t("offlineTickers", { list: health.offline_tickers?.join(", ") || "—" });
  return (
    <span className={`badge ${live ? "badge-live" : "badge-offline"}`} title={title}>
      <span className="dot" aria-hidden />
      {live ? t("liveData") : t("offlineData")}
    </span>
  );
}
