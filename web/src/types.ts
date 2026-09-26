// Mirrors src/cekfakta/schema.py. Keep in sync when the backend models change.
export type Lang = "id" | "en";
export interface Text {
  id: string;
  en: string;
}

export type Unit = "pct" | "idr" | "none";
export type ClaimType =
  | "revenue_growth"
  | "profit_growth"
  | "net_income"
  | "dividend_yield"
  | "market_cap"
  | "unverifiable";
export type VerdictLabel =
  | "Sesuai data"
  | "Sebagian sesuai"
  | "Tidak sesuai"
  | "Tidak dapat diverifikasi";

export interface Claim {
  ticker: string;
  claim_type: ClaimType;
  stated_value: number | null;
  unit: Unit;
  direction: "up" | "down" | null;
  period: string | null;
  source_text: string;
  unverifiable_reason: string | null;
  unverifiable_reason_en: string | null;
}

export interface Verdict {
  claim: Claim;
  label: VerdictLabel;
  actual_value: number | null;
  actual_unit: Unit;
  period_compared: Text | null;
  reason: Text;
  ok_range: [number, number] | null;
  partial_range: [number, number] | null;
}

export interface PriceMark {
  date: string;
  price: number;
}

export interface CompanySnapshot {
  ticker: string;
  name: string | null;
  sector: string | null;
  sub_sector: string | null;
  last_close_price: number | null;
  latest_close_date: string | null;
  daily_change_pct: number | null;
  market_cap: number | null;
  market_cap_rank: number | null;
  latest_quarter: string | null;
  yoy_revenue_growth_pct: number | null;
  yoy_earnings_growth_pct: number | null;
  dividend_yield_pct: number | null;
  eps: number | null;
  high_52w: PriceMark | null;
  low_52w: PriceMark | null;
  all_time_high: PriceMark | null;
  annual: { year: number; revenue: number | null; earnings: number | null }[];
  quarters: { date: string; revenue: number | null; earnings: number | null }[];
  dividends: { year: number; total: number | null; yield_pct: number | null }[];
  prices: { date: string; close: number }[];
}

export interface CheckResult {
  message: string;
  verdicts: Verdict[];
  companies: CompanySnapshot[];
  extractor: Extractor;
  model: string | null;
  data_source: "live" | "fixtures";
  credits_spent: number;
  notes: Text[];
  sources: SourceInfo[];
  media_text: string | null;
}

export type ProviderId = "anthropic" | "openai" | "gemini";
export type Extractor = ProviderId | "rules";

export interface ProviderInfo {
  id: ProviderId;
  label: string;
  key_prefix: string;
  default_model: string;
  server_key: boolean;
}

export interface LLMTestResult {
  ok: boolean;
  provider: Extractor;
  model: string | null;
  claims_found?: number;
  error?: Text;
}

export interface Health {
  status: string;
  version: string;
  data_source: "live" | "fixtures";
  llm_default: Extractor;
  allow_user_keys: boolean;
  providers: ProviderInfo[];
  bots?: { telegram: string | null; whatsapp: string | null };
  offline_tickers?: string[];
  credits_spent?: number;
  credit_cap?: number;
}

// Mirrors src/cekfakta/market.py.
export interface Quote {
  code: string;
  value: number;
  change_pct: number | null;
  date: string | null;
}
export interface SeriesPoint {
  date: string;
  value: number;
}
export interface MarketSnapshot {
  data_source: "live" | "fixtures";
  generated_at: string;
  ihsg: Quote | null;
  ihsg_series: SeriesPoint[];
  indices: Quote[];
  market_cap: Quote | null;
  market_cap_series: SeriesPoint[];
  gainers: { symbol: string; name: string | null; change_pct: number; price: number | null }[];
  losers: { symbol: string; name: string | null; change_pct: number; price: number | null }[];
  movers_date: string | null;
  most_traded: { symbol: string; name: string | null; volume: number; price: number | null }[];
  most_traded_date: string | null;
  commodities: { name: string; price: number; unit: string; change_pct: number | null; date: string }[];
  forex: { currency: string; rate: number; change_pct: number | null; date: string }[];
  news: { title: string; url: string; source: string; timestamp: string; symbols: string[] }[];
  unavailable: Record<string, "budget" | "error" | "offline">;
}

export interface WatchQuote {
  symbol: string;
  close: number | null;
  change_pct: number | null;
  date: string | null;
  series: SeriesPoint[];
  unavailable: "not_found" | "budget" | "offline" | "error" | null;
}

export type Platform = "web" | "youtube" | "tiktok" | "instagram" | "threads" | "facebook" | "x";
export interface SourceInfo {
  url: string;
  platform: Platform;
  status: "ok" | "partial" | "blocked" | "error";
  title: string | null;
  author: string | null;
  chars: number;
  note: Text | null;
  analyzed_video: boolean;
}
