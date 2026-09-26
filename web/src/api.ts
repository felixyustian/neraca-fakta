import { llmHeaders, type LLMSettings } from "./settings";
import type { CheckResult, Health, LLMTestResult, MarketSnapshot, WatchQuote } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies set their own multipart Content-Type (with boundary).
  const json = !(init?.body instanceof FormData);
  const res = await fetch(path, {
    ...init,
    headers: { ...(json ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>("/api/health");

export const checkMessage = (message: string, llm: LLMSettings) =>
  request<CheckResult>("/api/check", {
    method: "POST",
    body: JSON.stringify({ message }),
    headers: llmHeaders(llm),
  });

export function checkWithMedia(message: string, files: File[], llm: LLMSettings) {
  const form = new FormData();
  form.append("message", message);
  files.forEach((f) => form.append("files", f));
  return request<CheckResult>("/api/check-media", { method: "POST", body: form, headers: llmHeaders(llm) });
}

export const testLLM = (llm: LLMSettings) =>
  request<LLMTestResult>("/api/llm/test", { method: "POST", headers: llmHeaders(llm) });

export const getMarket = () => request<MarketSnapshot | null>("/api/market");

export const getWatchlist = (symbols: string[]) =>
  symbols.length
    ? request<WatchQuote[]>(`/api/watchlist?symbols=${encodeURIComponent(symbols.join(","))}`)
    : Promise.resolve([] as WatchQuote[]);
