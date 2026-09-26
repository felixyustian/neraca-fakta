import { useEffect, useRef, useState } from "react";
import { testLLM } from "./api";
import { useI18n } from "./i18n";
import { EMPTY_SETTINGS, type LLMSettings } from "./settings";
import type { Extractor, Health, LLMTestResult, ProviderInfo } from "./types";

interface Props {
  open: boolean;
  health: Health | null;
  settings: LLMSettings;
  onSave: (s: LLMSettings) => void;
  onClear: () => void;
  onClose: () => void;
}

export const PROVIDER_SHORT: Record<Exclude<Extractor, "rules">, string> = {
  anthropic: "Claude",
  openai: "OpenAI",
  gemini: "Gemini",
};

export function providerName(p: Extractor, noAI: string): string {
  return p === "rules" ? noAI : PROVIDER_SHORT[p];
}

export default function SettingsDialog({ open, health, settings, onSave, onClear, onClose }: Props) {
  const { t, tx } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState<LLMSettings>(settings);
  const [showKey, setShowKey] = useState(false);
  const [test, setTest] = useState<LLMTestResult | { ok: false; errorText: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setDraft(settings);
      setTest(null);
      setShowKey(false);
      d.showModal();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open, settings]);

  const providers = health?.providers ?? [];
  const serverDefault = health?.llm_default ?? "rules";
  const effective: Extractor = draft.provider || serverDefault;
  const info: ProviderInfo | undefined = providers.find((p) => p.id === effective);
  const key = draft.provider ? draft.keys[draft.provider] ?? "" : "";
  const model = draft.provider ? draft.models[draft.provider] ?? "" : "";
  const allowKeys = health?.allow_user_keys ?? true;
  const prefixWarning = info && key && !key.trim().startsWith(info.key_prefix);
  const needsKey = draft.provider && draft.provider !== "rules" && !key.trim() && !info?.server_key;

  function set(patch: Partial<LLMSettings>) {
    setDraft((d) => ({ ...d, ...patch }));
    setTest(null);
  }

  function setField(field: "keys" | "models", v: string) {
    if (!draft.provider) return;
    set({ [field]: { ...draft[field], [draft.provider]: v } });
  }

  async function runTest() {
    setTesting(true);
    setTest(null);
    try {
      setTest(await testLLM(draft));
    } catch (e) {
      setTest({ ok: false, errorText: e instanceof Error ? e.message : t("testFail") });
    } finally {
      setTesting(false);
    }
  }

  const options: { id: LLMSettings["provider"]; title: string; sub: string }[] = [
    {
      id: "",
      title: t("serverDefault"),
      sub: t("currently", { p: providerName(serverDefault, t("noAI")) }),
    },
    ...providers.map((p) => ({
      id: p.id as LLMSettings["provider"],
      title: p.label,
      sub: p.server_key ? t("serverKey") : t("needsKey"),
    })),
    { id: "rules", title: t("noAI"), sub: t("noAISub") },
  ];

  return (
    <dialog ref={ref} className="dialog" onClose={onClose} aria-labelledby="settings-title">
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(draft);
        }}
      >
        <div className="dialog-head">
          <h2 id="settings-title">{t("aiSettings")}</h2>
          <button type="button" className="icon-btn" aria-label={t("closeLabel")} onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="muted small">{t("aiIntro")}</p>

        <fieldset className="providers">
          <legend className="field-label">{t("provider")}</legend>
          {options.map((o) => (
            <label key={o.id || "default"} className={`provider ${draft.provider === o.id ? "selected" : ""}`}>
              <input
                type="radio"
                name="provider"
                checked={draft.provider === o.id}
                onChange={() => set({ provider: o.id })}
              />
              <span>
                <strong>{o.title}</strong>
                <span className="muted small">{o.sub}</span>
              </span>
            </label>
          ))}
        </fieldset>

        {draft.provider && draft.provider !== "rules" && info && (
          <div className="key-fields">
            <label className="field-label" htmlFor="api-key">
              {t("apiKeyFor", { p: info.label })}
            </label>
            <div className="key-row">
              <input
                id="api-key"
                type={showKey ? "text" : "password"}
                value={key}
                onChange={(e) => setField("keys", e.target.value)}
                placeholder={
                  !allowKeys
                    ? t("keyServerOnly")
                    : info.server_key
                      ? t("keyUseServer")
                      : t("keyPaste", { p: info.label, x: info.key_prefix })
                }
                disabled={!allowKeys}
                autoComplete="off"
                spellCheck={false}
              />
              <button type="button" className="ghost" onClick={() => setShowKey((v) => !v)} disabled={!allowKeys}>
                {showKey ? t("hide") : t("show")}
              </button>
            </div>
            {prefixWarning && (
              <p className="hint warn">{t("prefixWarn", { p: info.label, x: info.key_prefix })}</p>
            )}

            <label className="field-label" htmlFor="model">
              {t("model")} <span className="muted small">{t("optional")}</span>
            </label>
            <input
              id="model"
              type="text"
              value={model}
              onChange={(e) => setField("models", e.target.value)}
              placeholder={info.default_model}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}

        <label className="check">
          <input type="checkbox" checked={draft.remember} onChange={(e) => set({ remember: e.target.checked })} />
          {t("remember")}
        </label>
        <p className="muted small">{t("keyPrivacy", { when: draft.remember ? t("untilCleared") : t("untilTabClosed") })}</p>

        {test && (
          <p className={`hint ${test.ok ? "good" : "warn"}`} role="status">
            {"errorText" in test
              ? test.errorText
              : test.ok
                ? test.provider !== "rules"
                  ? t("testOk", { p: PROVIDER_SHORT[test.provider], m: test.model ?? "" })
                  : t("testRules")
                : tx(test.error)}
          </p>
        )}

        <div className="dialog-actions">
          <button
            type="button"
            className="ghost danger"
            onClick={() => {
              setDraft(EMPTY_SETTINGS);
              setTest(null);
              onClear();
            }}
          >
            {t("clearKeys")}
          </button>
          <span className="spacer" />
          <button type="button" className="ghost" onClick={runTest} disabled={testing || !!needsKey}>
            {testing ? t("testing") : t("testConn")}
          </button>
          <button type="submit" className="primary" disabled={!!needsKey}>
            {t("save")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
