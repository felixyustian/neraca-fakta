"""Deterministic verdicts: compare one extracted Claim against CompanyFacts.

No LLM here. Every verdict carries the number it was compared with, the period,
a one-line reason in Indonesian and English, and the tolerance bands used, so a
reader can check the check.

Tolerances (claims in tips are usually rounded):
- growth %:        Sesuai within max(2 pp, 10% of actual); Sebagian if same direction
                   and within max(5 pp, 50% of actual)
- dividend yield:  Sesuai within 0.5 pp; Sebagian within 1.5 pp
- IDR amounts:     Sesuai within 5%; Sebagian within 20% (market cap: 15%)
"""
from __future__ import annotations

import re

from .facts import CompanyFacts
from .schema import Claim, ClaimType, Text, Verdict, VerdictLabel

_QUARTER_RE = re.compile(r"(?:\bQ|kuartal\s*|triwulan\s*)(IV|I{1,3}|[1-4])\b\D*(20\d{2})?", re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
_IDR_UNITS = {"id": ("triliun", "miliar", "juta"), "en": ("trillion", "billion", "million")}


# --- formatting ------------------------------------------------------------------

def fmt_num(x: float, decimals: int = 1, lang: str = "id") -> str:
    """6.1 -> '6,1' (id) / '6.1' (en); thousands grouped."""
    s = f"{x:,.{decimals}f}"
    if lang == "id":
        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return s


def fmt_pct(x: float, lang: str = "id") -> str:
    return ("+" if x > 0 else "") + fmt_num(x, 1, lang) + "%"


def fmt_idr(x: float, lang: str = "id") -> str:
    sign, a = ("-" if x < 0 else ""), abs(x)
    for div, unit in zip((1e12, 1e9, 1e6), _IDR_UNITS[lang]):
        if a >= div:
            return f"{sign}Rp{fmt_num(a / div, 2, lang)} {unit}"
    return f"{sign}Rp{fmt_num(a, 0, lang)}"


def quarter_label(date: str | None) -> str | None:
    """'2026-06-30' -> 'Q2 2026'."""
    if not date:
        return None
    year, month = int(date[:4]), int(date[5:7])
    return f"Q{(month - 1) // 3 + 1} {year}"


def parse_quarter(period: str | None) -> tuple[int, int | None] | None:
    if not period:
        return None
    m = _QUARTER_RE.search(period)
    if not m:
        return None
    q = m.group(1).upper()
    return (_ROMAN.get(q) or int(q), int(m.group(2)) if m.group(2) else None)


def _is_qoq(period: str | None) -> bool:
    return bool(period) and bool(re.search(r"qoq|kuartal (lalu|sebelumnya)|quarter", period, re.I))


# --- verdict builders ------------------------------------------------------------

def _verdict(claim: Claim, label: VerdictLabel, reason: Text, actual=None, unit="none",
             period: Text | None = None, ok=None, partial=None) -> Verdict:
    return Verdict(claim=claim, label=label, actual_value=actual, actual_unit=unit,
                   period_compared=period, reason=reason, ok_range=ok, partial_range=partial)


def _cannot(claim: Claim, reason: Text) -> Verdict:
    return _verdict(claim, VerdictLabel.TIDAK_DAPAT, reason)


def _period_mismatch(claim: Claim, latest: str | None) -> Text | None:
    """Reason if the claim names a quarter other than the latest one we have."""
    pq = parse_quarter(claim.period)
    if not pq or not latest:
        return None
    q, year = pq
    lq, ly = int(latest[1]), int(latest[3:])
    if q != lq or (year is not None and year != ly):
        return Text(
            id=f"Klaim menyebut {claim.period}, sedangkan data yang tersedia adalah kuartal "
               f"terakhir ({latest}). Periode lain belum didukung.",
            en=f"The claim refers to {claim.period}, but the available data is the latest "
               f"quarter ({latest}). Other periods aren't supported yet.",
        )
    return None


def _band(center: float, half: float) -> tuple[float, float]:
    return (center - half, center + half)


def _grade_growth(claim: Claim, actual: float, period: Text) -> Verdict:
    stated = claim.stated_value
    if stated is not None and claim.direction == "down" and stated > 0:
        stated = -stated
    ok_half = max(2.0, 0.10 * abs(actual))
    partial_half = max(5.0, 0.50 * abs(actual))
    ok = _band(actual, ok_half)
    lo, hi = _band(actual, partial_half)
    partial = (max(lo, 0.0), hi) if actual >= 0 else (lo, min(hi, 0.0))  # same direction only

    if stated is None:
        if claim.direction is None:
            return _cannot(claim, Text(id="Klaim tidak menyebut angka maupun arah pertumbuhan.",
                                       en="The claim gives neither a number nor a direction."))
        claimed_up = claim.direction != "down"
        label = VerdictLabel.SESUAI if claimed_up == (actual >= 0) else VerdictLabel.TIDAK_SESUAI
        reason = Text(
            id=f"Data menunjukkan {'naik' if actual >= 0 else 'turun'} {fmt_pct(actual, 'id')} ({period.id}).",
            en=f"The data shows {'growth' if actual >= 0 else 'a decline'} of {fmt_pct(actual, 'en')} ({period.en}).",
        )
        return _verdict(claim, label, reason, actual, "pct", period)

    diff = abs(stated - actual)
    same_direction = (stated >= 0) == (actual >= 0)
    if diff <= ok_half:
        label, how = VerdictLabel.SESUAI, {"id": "sesuai", "en": "matches"}
    elif same_direction and diff <= partial_half:
        label, how = VerdictLabel.SEBAGIAN, {"id": "arahnya benar, tetapi angkanya meleset",
                                             "en": "right direction, but the number is off"}
    else:
        label, how = VerdictLabel.TIDAK_SESUAI, {"id": "tidak sesuai", "en": "does not match"}
    reason = Text(
        id=f"Klaim {fmt_pct(stated, 'id')}, data {fmt_pct(actual, 'id')} ({period.id}): {how['id']}.",
        en=f"Claimed {fmt_pct(stated, 'en')}, data {fmt_pct(actual, 'en')} ({period.en}): {how['en']}.",
    )
    return _verdict(claim, label, reason, actual, "pct", period, ok, partial)


def _grade_amount(claim: Claim, actual: float, period: Text, what: Text,
                  ok: float = 0.05, partial: float = 0.20) -> Verdict:
    if claim.stated_value is None:
        reason = Text(
            id=f"Klaim tidak menyebut angka. Sebagai rujukan, {what.id} {fmt_idr(actual, 'id')} ({period.id}).",
            en=f"The claim gives no number. For reference, {what.en} was {fmt_idr(actual, 'en')} ({period.en}).",
        )
        return _verdict(claim, VerdictLabel.TIDAK_DAPAT, reason, actual, "idr", period)
    if actual == 0:
        return _cannot(claim, Text(id=f"{what.id.capitalize()} tercatat nol; tidak bisa dibandingkan.",
                                   en=f"{what.en.capitalize()} is recorded as zero; nothing to compare."))
    ok_band = tuple(sorted((actual * (1 - ok), actual * (1 + ok))))
    partial_band = tuple(sorted((actual * (1 - partial), actual * (1 + partial))))
    rel = abs(claim.stated_value - actual) / abs(actual)
    label = (VerdictLabel.SESUAI if rel <= ok else
             VerdictLabel.SEBAGIAN if rel <= partial else VerdictLabel.TIDAK_SESUAI)
    reason = Text(
        id=f"Klaim {fmt_idr(claim.stated_value, 'id')}, data {fmt_idr(actual, 'id')} ({period.id}), "
           f"selisih {rel * 100:.0f}%.",
        en=f"Claimed {fmt_idr(claim.stated_value, 'en')}, data {fmt_idr(actual, 'en')} ({period.en}), "
           f"{rel * 100:.0f}% apart.",
    )
    return _verdict(claim, label, reason, actual, "idr", period, ok_band, partial_band)


def verify(claim: Claim, facts: CompanyFacts | None) -> Verdict:
    if claim.claim_type == ClaimType.UNVERIFIABLE:
        return _cannot(claim, Text(
            id=claim.unverifiable_reason or "Klaim ini bukan fakta yang tercatat di data keuangan.",
            en=claim.unverifiable_reason_en or "This claim is not a fact recorded in financial data.",
        ))
    if facts is None:
        return _cannot(claim, Text(id=f"Data untuk {claim.ticker} tidak ditemukan.",
                                   en=f"No data found for {claim.ticker}."))

    latest = quarter_label((facts.quarter(0) or {}).get("date"))

    if claim.claim_type in (ClaimType.REVENUE_GROWTH, ClaimType.PROFIT_GROWTH):
        is_rev = claim.claim_type == ClaimType.REVENUE_GROWTH
        if _is_qoq(claim.period):
            actual = facts.qoq_growth_pct("revenue" if is_rev else "earnings")
            prev = quarter_label((facts.quarter(1) or {}).get("date"))
            period = Text(id=f"{latest} vs {prev} (QoQ)", en=f"{latest} vs {prev} (QoQ)")
        else:
            if mismatch := _period_mismatch(claim, latest):
                return _cannot(claim, mismatch)
            actual = facts.yoy_revenue_growth_pct if is_rev else facts.yoy_earnings_growth_pct
            period = Text(id=f"{latest or 'kuartal terakhir'} vs tahun sebelumnya (YoY)",
                          en=f"{latest or 'latest quarter'} vs a year earlier (YoY)")
        if actual is None:
            return _cannot(claim, Text(id="Data pertumbuhan untuk periode ini tidak tersedia.",
                                       en="Growth data for this period isn't available."))
        return _grade_growth(claim, actual, period)

    if claim.claim_type == ClaimType.NET_INCOME:
        pq = parse_quarter(claim.period)
        year = _YEAR_RE.search(claim.period or "")
        if year and not pq:
            y = int(year.group(1))
            rows = facts._section("financials").get("historical_financials") or []
            row = next((r for r in rows if r.get("year") == y), None)
            if not row or row.get("earnings") is None:
                return _cannot(claim, Text(id=f"Laba bersih tahun {y} tidak ada di data.",
                                           en=f"Net income for {y} isn't in the data."))
            return _grade_amount(claim, row["earnings"], Text(id=f"tahun {y}", en=f"full year {y}"),
                                 Text(id="laba bersih", en="net income"))
        if mismatch := _period_mismatch(claim, latest):
            return _cannot(claim, mismatch)
        q0 = facts.quarter(0)
        if not q0 or q0.get("earnings") is None:
            return _cannot(claim, Text(id="Laba bersih kuartal terakhir tidak tersedia.",
                                       en="Net income for the latest quarter isn't available."))
        return _grade_amount(claim, q0["earnings"],
                             Text(id=latest or "kuartal terakhir", en=latest or "latest quarter"),
                             Text(id="laba bersih kuartalan", en="quarterly net income"))

    if claim.claim_type == ClaimType.DIVIDEND_YIELD:
        actual = facts.dividend_yield_pct
        if actual is None:
            return _cannot(claim, Text(id="Tidak ada data dividen 12 bulan terakhir untuk emiten ini.",
                                       en="No dividend data for the last 12 months for this company."))
        period = Text(id="12 bulan terakhir (TTM)", en="trailing 12 months (TTM)")
        if claim.stated_value is None:
            return _verdict(claim, VerdictLabel.TIDAK_DAPAT, Text(
                id=f"Klaim tidak menyebut angka. Yield TTM tercatat {fmt_num(actual, 2, 'id')}%.",
                en=f"The claim gives no number. TTM yield is {fmt_num(actual, 2, 'en')}%.",
            ), actual, "pct", period)
        diff = abs(claim.stated_value - actual)
        label = (VerdictLabel.SESUAI if diff <= 0.5 else
                 VerdictLabel.SEBAGIAN if diff <= 1.5 else VerdictLabel.TIDAK_SESUAI)
        reason = Text(
            id=f"Klaim yield {fmt_num(claim.stated_value, 1, 'id')}%, data {fmt_num(actual, 2, 'id')}% ({period.id}).",
            en=f"Claimed yield {fmt_num(claim.stated_value, 1, 'en')}%, data {fmt_num(actual, 2, 'en')}% ({period.en}).",
        )
        return _verdict(claim, label, reason, actual, "pct", period,
                        _band(actual, 0.5), (max(0.0, actual - 1.5), actual + 1.5))

    if claim.claim_type == ClaimType.MARKET_CAP:
        if facts.market_cap is None:
            return _cannot(claim, Text(id="Data kapitalisasi pasar tidak tersedia.",
                                       en="Market cap data isn't available."))
        date = facts._section("overview").get("latest_close_date")
        period = Text(id=f"per {date}" if date else "penutupan terakhir",
                      en=f"as of {date}" if date else "last close")
        return _grade_amount(claim, facts.market_cap, period,
                             Text(id="kapitalisasi pasar", en="market cap"), partial=0.15)

    return _cannot(claim, Text(id="Jenis klaim ini belum didukung.",
                               en="This claim type isn't supported yet."))
