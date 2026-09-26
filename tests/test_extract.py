"""Rule-based extractor on typical Indonesian tip phrasing."""
from __future__ import annotations

from cekfakta.extract import RuleExtractor, find_tickers
from cekfakta.schema import ClaimType


def extract(text):
    return RuleExtractor().extract(text)


def test_growth_claims_and_hype():
    claims = extract("🔥 $GOTO laba Q2 2026 naik 200% YoY! Pendapatan tumbuh 30%. "
                     "Target 100 minggu depan, pasti ARA!")
    assert [c.claim_type for c in claims] == [
        ClaimType.PROFIT_GROWTH, ClaimType.REVENUE_GROWTH, ClaimType.UNVERIFIABLE]
    assert claims[0].stated_value == 200 and claims[0].direction == "up"
    assert claims[0].period == "Q2 2026"
    assert all(c.ticker == "GOTO" for c in claims)


def test_two_claims_in_one_sentence_keep_their_own_numbers():
    profit, revenue = extract("BBCA laba turun 15% yoy, pendapatan naik 1,5% QoQ")
    assert (profit.claim_type, profit.stated_value, profit.direction) == (ClaimType.PROFIT_GROWTH, 15, "down")
    assert (revenue.claim_type, revenue.stated_value, revenue.period) == (ClaimType.REVENUE_GROWTH, 1.5, "QoQ")


def test_idr_amounts():
    yld, cap, ni = extract("TLKM dividen yield 12%, market cap Rp 240 T. "
                           "Laba bersih kuartal ini Rp 6,3 triliun")
    assert (yld.claim_type, yld.stated_value) == (ClaimType.DIVIDEND_YIELD, 12)
    assert (cap.claim_type, cap.stated_value) == (ClaimType.MARKET_CAP, 240e12)
    assert (ni.claim_type, ni.stated_value, ni.period) == (ClaimType.NET_INCOME, 6.3e12, None)


def test_company_names_and_non_tickers():
    assert find_tickers("Saham Telkom WAJIB BELI, BBRI juga") == ["BBRI", "TLKM"]
    assert extract("halo apa kabar") == []
