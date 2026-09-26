import type { Extractor } from "./types";

// The user's LLM choice. Lives only in this browser: sessionStorage by default,
// localStorage when "remember" is on. Sent to our API as headers with each check.
export interface LLMSettings {
  provider: Extractor | ""; // "" = use the server's default
  keys: Partial<Record<Extractor, string>>; // one key per provider, so switching doesn't lose them
  models: Partial<Record<Extractor, string>>;
  remember: boolean;
}

const STORAGE_KEY = "cekfakta.llm";
export const EMPTY_SETTINGS: LLMSettings = { provider: "", keys: {}, models: {}, remember: false };

function read(store: () => Storage): LLMSettings | null {
  try {
    const raw = store().getItem(STORAGE_KEY);
    return raw ? { ...EMPTY_SETTINGS, ...JSON.parse(raw) } : null;
  } catch {
    return null; // private mode, blocked storage, or corrupt JSON
  }
}

export function loadSettings(): LLMSettings {
  return read(() => sessionStorage) ?? read(() => localStorage) ?? EMPTY_SETTINGS;
}

export function saveSettings(s: LLMSettings): void {
  try {
    // Keep exactly one copy, in the store the user chose.
    const [keep, drop] = s.remember ? [localStorage, sessionStorage] : [sessionStorage, localStorage];
    drop.removeItem(STORAGE_KEY);
    keep.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* settings still apply for this page load */
  }
}

export function clearSettings(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing stored */
  }
}

export function llmHeaders(s: LLMSettings): Record<string, string> {
  if (!s.provider) return {};
  const h: Record<string, string> = { "X-LLM-Provider": s.provider };
  const key = s.keys[s.provider]?.trim();
  const model = s.models[s.provider]?.trim();
  if (key) h["X-LLM-Key"] = key;
  if (model) h["X-LLM-Model"] = model;
  return h;
}
