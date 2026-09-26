"""Typed contracts between pipeline steps. The LLM fills Claim; code fills Verdict."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Text(BaseModel):
    """User-facing text in both UI languages."""
    id: str
    en: str


class ClaimType(str, Enum):
    REVENUE_GROWTH = "revenue_growth"
    PROFIT_GROWTH = "profit_growth"
    NET_INCOME = "net_income"
    DIVIDEND_YIELD = "dividend_yield"
    MARKET_CAP = "market_cap"
    UNVERIFIABLE = "unverifiable"


class Claim(BaseModel):
    ticker: str = Field(description="IDX code after resolution, e.g. 'BBRI'")
    claim_type: ClaimType
    stated_value: float | None = Field(None, description="200.0 for 'naik 200%'")
    unit: Literal["pct", "idr", "none"] = "none"
    direction: Literal["up", "down"] | None = Field(
        None, description="'naik' -> up, 'turun' -> down; set even when no number is given")
    period: str | None = Field(None, description="'Q2 2026', 'YoY', 'QoQ', '2025', or None if unstated")
    source_text: str = Field(description="Exact span from the message")
    unverifiable_reason: str | None = None
    unverifiable_reason_en: str | None = None


class VerdictLabel(str, Enum):
    SESUAI = "Sesuai data"
    SEBAGIAN = "Sebagian sesuai"
    TIDAK_SESUAI = "Tidak sesuai"
    TIDAK_DAPAT = "Tidak dapat diverifikasi"


class Verdict(BaseModel):
    claim: Claim
    label: VerdictLabel
    actual_value: float | None = None
    actual_unit: Literal["pct", "idr", "none"] = "none"
    period_compared: Text | None = None
    reason: Text
    # Stated values inside ok_range grade "Sesuai", inside partial_range "Sebagian" (drawn as
    # the tolerance bands on the UI's gauge). None when no numeric comparison was made.
    ok_range: tuple[float, float] | None = None
    partial_range: tuple[float, float] | None = None


class AnnualPoint(BaseModel):
    year: int
    revenue: float | None = None
    earnings: float | None = None


class QuarterPoint(BaseModel):
    date: str
    revenue: float | None = None
    earnings: float | None = None


class DividendPoint(BaseModel):
    year: int
    total: float | None = Field(None, description="IDR per share")
    yield_pct: float | None = None


class PricePoint(BaseModel):
    date: str
    close: float


class PriceMark(BaseModel):
    date: str
    price: float


class CompanySnapshot(BaseModel):
    """Everything the UI shows about a company: headline numbers and chart series."""
    ticker: str
    name: str | None = None
    sector: str | None = None
    sub_sector: str | None = None
    last_close_price: float | None = None
    latest_close_date: str | None = None
    daily_change_pct: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    latest_quarter: str | None = None
    yoy_revenue_growth_pct: float | None = None
    yoy_earnings_growth_pct: float | None = None
    dividend_yield_pct: float | None = None
    eps: float | None = None
    high_52w: PriceMark | None = None
    low_52w: PriceMark | None = None
    all_time_high: PriceMark | None = None
    annual: list[AnnualPoint] = []
    quarters: list[QuarterPoint] = []
    dividends: list[DividendPoint] = []
    prices: list[PricePoint] = Field([], description="Daily closes, up to ~90 days")


Platform = Literal["web", "youtube", "tiktok", "instagram", "threads", "facebook", "x"]
SourceStatus = Literal["ok", "partial", "blocked", "error"]


class Source(BaseModel):
    url: str
    platform: Platform
    status: SourceStatus
    title: str | None = None
    author: str | None = None
    text: str = ""
    video_url: str | None = None  # set for YouTube: Gemini can analyse the video itself
    note: Text | None = None


class SourceInfo(BaseModel):
    """What the UI and bots show about a source (no full text)."""
    url: str
    platform: Platform
    status: SourceStatus
    title: str | None = None
    author: str | None = None
    chars: int = 0
    note: Text | None = None
    analyzed_video: bool = False

    @classmethod
    def of(cls, s: Source, analyzed_video: bool = False) -> "SourceInfo":
        return cls(url=s.url, platform=s.platform, status=s.status, title=s.title, author=s.author,
                   chars=len(s.text), note=s.note, analyzed_video=analyzed_video)


class CheckResult(BaseModel):
    message: str
    verdicts: list[Verdict]
    companies: list[CompanySnapshot]
    extractor: Literal["anthropic", "openai", "gemini", "rules"]
    model: str | None = Field(None, description="LLM model used; None for the rule extractor")
    data_source: Literal["live", "fixtures"]
    credits_spent: int = Field(0, description="Sectors credits this check cost (0 on cache hits)")
    notes: list[Text] = []
    # Links in the message that were read (web, YouTube, TikTok, social), and the text the
    # AI read from attached screenshots or a video.
    sources: list[SourceInfo] = []
    media_text: str | None = None
