"""Rule-based claim extraction: regex over Indonesian tip phrasing.

No key, no network. Runs when no LLM provider is configured, and as the fallback when an
LLM call fails (see llm.py for the Anthropic / OpenAI / Gemini extractors).
"""
from __future__ import annotations

import re

from .schema import Claim, ClaimType

_TICKER_RE = re.compile(r"\$?\b([A-Z]{4})(?:\.JK)?\b")
# All-caps words common in tips that look like tickers but are not.
_NOT_TICKERS = {
    "BELI", "JUAL", "HOLD", "WAJIB", "CUAN", "INFO", "HARI", "BARU", "SAHAM", "RUGI",
    "NAIK", "BIG", "LABA", "YANG", "AKAN", "BISA", "SAJA", "JUGA", "UNTUK", "DARI",
    "SIAP", "GASS", "GASPOL", "STOP", "LOSS", "TAKE", "SELL", "HALF", "FULL", "PASTI",
    "YUK", "AYO", "SEGERA", "CEPAT", "BOOM", "MOON", "TERBANG", "DONG", "BUKAN",
    # Acronyms common in Indonesian market articles (each false "ticker" would cost a credit).
    "IHSG", "BUMN", "BPJS", "APBN", "APBD", "RUPS", "KPPU", "NPWP", "KSEI", "JKSE", "EBIT", "CAGR",
    "NEWS", "LIVE", "VIDEO", "BACA", "FOTO", "HTTP", "HTML", "HTTPS", "RINGKASAN",
}
# Common names forwarded instead of codes.
_NAME_TO_TICKER = {
    "telkom": "TLKM", "bca": "BBCA", "bank central asia": "BBCA", "goto": "GOTO",
    "gojek": "GOTO", "tokopedia": "GOTO", "bri": "BBRI", "bank rakyat": "BBRI",
    "mandiri": "BMRI", "bni": "BBNI", "astra": "ASII", "antam": "ANTM", "unilever": "UNVR",
}

_KEYWORDS: list[tuple[ClaimType, re.Pattern[str]]] = [
    (ClaimType.MARKET_CAP, re.compile(r"market\s*cap|kapitalisasi", re.I)),
    (ClaimType.DIVIDEND_YIELD, re.compile(r"dividen|dividend|\byield\b", re.I)),
    (ClaimType.REVENUE_GROWTH, re.compile(r"pendapatan|penjualan|revenue|omzet|omset", re.I)),
    (ClaimType.PROFIT_GROWTH, re.compile(r"laba|profit|earning|keuntungan|untung", re.I)),
]
_UP = re.compile(r"naik|tumbuh|melonjak|meroket|melesat|terbang|meningkat|bertambah|up\b|\+", re.I)
_DOWN = re.compile(r"turun|anjlok|merosot|jatuh|menurun|ambles|longsor|down\b", re.I)
_PCT_RE = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s*(?:%|persen)", re.I)
_IDR_RE = re.compile(
    r"(?:rp\.?\s*)?(\d+(?:[.,]\d+)?)\s*(triliun|trilyun|t\b|miliar|milyar|m\b|b\b|juta|jt\b)", re.I)
_SCALE = {"t": 1e12, "triliun": 1e12, "trilyun": 1e12, "miliar": 1e9, "milyar": 1e9,
          "m": 1e9, "b": 1e9, "juta": 1e6, "jt": 1e6}
_PERIOD_RE = re.compile(
    r"(Q[1-4]\s*20\d{2}|kuartal\s*(?:IV|I{1,3}|[1-4])\b\s*(?:20\d{2})?|yoy|qoq|"
    r"kuartal (?:lalu|sebelumnya)|tahun (?:lalu|20\d{2})|\b20\d{2}\b)", re.I)
_FORECAST = re.compile(
    r"target|\btp\b|pasti|dijamin|bakal|akan|besok|minggu depan|bulan depan|\bara\b|"
    r"auto reject|to the moon|bandar|akumulasi|orang dalam|insider|rekomendasi|"
    r"multibagger|cuan \d+", re.I)


def _num(s: str) -> float:
    """'1,5' -> 1.5; '1.000' -> 1000; '2.5' -> 2.5."""
    if "," in s:
        return float(s.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return float(s.replace(".", ""))
    return float(s)


def find_tickers(text: str) -> list[str]:
    found: list[str] = []
    for m in _TICKER_RE.finditer(text):
        t = m.group(1)
        if t not in _NOT_TICKERS and t not in found:
            found.append(t)
    lower = text.lower()
    for name, t in _NAME_TO_TICKER.items():
        if re.search(rf"\b{re.escape(name)}\b", lower) and t not in found:
            found.append(t)
    return found


def _sentences(text: str) -> list[str]:
    # Clauses, not just sentences: "laba naik 20%, pendapatan turun 5%" holds two claims.
    # ",\s" keeps decimal commas ("Rp 6,3 T") intact.
    parts = re.split(r"(?<=[.!?;])\s+|\n+|,\s+|\s+(?:dan|serta|sementara)\s+", text)
    return [p.strip(" -•*") for p in parts if p and p.strip(" -•*")]


class RuleExtractor:
    name = "rules"

    def extract(self, message: str) -> list[Claim]:
        claims: list[Claim] = []
        current: str | None = None
        for sent in _sentences(message):
            tickers = find_tickers(sent)
            if tickers:
                current = tickers[0]
            if current is None:
                continue
            period_m = _PERIOD_RE.search(sent)
            period = period_m.group(1) if period_m else None
            matched = False
            for ctype, kw in _KEYWORDS:
                if not kw.search(sent):
                    continue
                claim = self._claim(ctype, current, sent, period)
                if claim:
                    claims.append(claim)
                    matched = True
                    break
            if not matched and _FORECAST.search(sent):
                prev = claims[-1] if claims else None
                if prev and prev.claim_type == ClaimType.UNVERIFIABLE and prev.ticker == current:
                    prev.source_text += ", " + sent  # one card for a run of hype clauses
                    continue
                claims.append(Claim(
                    ticker=current, claim_type=ClaimType.UNVERIFIABLE, source_text=sent,
                    unverifiable_reason="Prediksi, janji, atau rumor; tidak bisa dicek dengan "
                                        "data keuangan yang sudah dilaporkan.",
                    unverifiable_reason_en="A prediction, promise, or rumour; it can't be checked "
                                           "against reported financial data.",
                ))
        return claims

    @staticmethod
    def _claim(ctype: ClaimType, ticker: str, sent: str, period: str | None) -> Claim | None:
        direction = "down" if _DOWN.search(sent) else "up" if _UP.search(sent) else None
        pct = _PCT_RE.search(sent)
        idr = _IDR_RE.search(sent)

        if ctype in (ClaimType.MARKET_CAP,):
            if not idr:
                return None
            value = _num(idr.group(1)) * _SCALE[idr.group(2).lower()]
            return Claim(ticker=ticker, claim_type=ctype, stated_value=value, unit="idr",
                         period=period, source_text=sent)
        if ctype == ClaimType.DIVIDEND_YIELD:
            if not pct:
                return None
            return Claim(ticker=ticker, claim_type=ctype, stated_value=abs(_num(pct.group(1))),
                         unit="pct", period=period, source_text=sent)
        # Growth claims need a percentage or a direction; a bare IDR amount is net income.
        if pct or (direction and not idr):
            value = abs(_num(pct.group(1))) if pct else None
            if pct and pct.group(1).startswith("-"):
                direction = "down"
            return Claim(ticker=ticker, claim_type=ctype, stated_value=value,
                         unit="pct" if pct else "none", direction=direction,
                         period=period, source_text=sent)
        if idr and ctype == ClaimType.PROFIT_GROWTH:
            value = _num(idr.group(1)) * _SCALE[idr.group(2).lower()]
            return Claim(ticker=ticker, claim_type=ClaimType.NET_INCOME, stated_value=value,
                         unit="idr", period=period, source_text=sent)
        return None

