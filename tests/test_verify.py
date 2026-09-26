"""Verifier: tolerances, periods, and directions. Pure functions, no I/O."""
from __future__ import annotations

import pytest

from cekfakta.schema import Claim, ClaimType, VerdictLabel as L
from cekfakta.verify import parse_quarter, verify


def claim(ctype, value=None, unit="pct", period=None, direction=None):
    return Claim(ticker="TLKM", claim_type=ctype, stated_value=value, unit=unit,
                 period=period, direction=direction, source_text="x")


@pytest.mark.parametrize("value,direction,expected", [
    (20, "up", L.SESUAI),         # actual +21.6%
    (30, "up", L.SEBAGIAN),       # right direction, off by 8.4 pp
    (200, "up", L.TIDAK_SESUAI),
    (20, "down", L.TIDAK_SESUAI), # wrong direction
    (None, "up", L.SESUAI),       # direction-only claim
    (None, "down", L.TIDAK_SESUAI),
])
def test_profit_growth_yoy(facts, value, direction, expected):
    v = verify(claim(ClaimType.PROFIT_GROWTH, value, direction=direction), facts)
    assert v.label == expected
    assert v.actual_value == pytest.approx(21.6)


def test_qoq_uses_quarterly_numbers(facts):
    v = verify(claim(ClaimType.PROFIT_GROWTH, 45, period="QoQ", direction="up"), facts)
    assert v.actual_value == pytest.approx((6279 - 4344) / 4344 * 100)
    assert v.label == L.SESUAI
    assert "QoQ" in v.period_compared.id


def test_other_quarter_is_not_guessed(facts):
    v = verify(claim(ClaimType.PROFIT_GROWTH, 20, period="Q1 2026", direction="up"), facts)
    assert v.label == L.TIDAK_DAPAT


def test_net_income_quarter_and_year(facts):
    assert verify(claim(ClaimType.NET_INCOME, 6.3e12, "idr"), facts).label == L.SESUAI
    v = verify(claim(ClaimType.NET_INCOME, 20e12, "idr", period="2025"), facts)
    assert v.label == L.SEBAGIAN and v.period_compared.en == "full year 2025"


@pytest.mark.parametrize("value,expected", [(9.5, L.SESUAI), (10.5, L.SEBAGIAN), (12, L.TIDAK_SESUAI)])
def test_dividend_yield(facts, value, expected):
    assert verify(claim(ClaimType.DIVIDEND_YIELD, value), facts).label == expected


def test_market_cap(facts):
    assert verify(claim(ClaimType.MARKET_CAP, 250e12, "idr"), facts).label == L.SESUAI
    assert verify(claim(ClaimType.MARKET_CAP, 400e12, "idr"), facts).label == L.TIDAK_SESUAI


def test_unverifiable_and_missing_data(facts):
    c = claim(ClaimType.UNVERIFIABLE)
    c.unverifiable_reason = "target harga"
    v = verify(c, facts)
    assert v.reason.id == "target harga"
    assert v.reason.en  # falls back to a generic English reason
    assert verify(claim(ClaimType.MARKET_CAP, 1e12, "idr"), None).label == L.TIDAK_DAPAT


@pytest.mark.parametrize("text,expected", [
    ("Q2 2026", (2, 2026)), ("kuartal III 2025", (3, 2025)), ("kuartal 4", (4, None)),
    ("kuartal ini", None), ("YoY", None), (None, None),
])
def test_parse_quarter(text, expected):
    assert parse_quarter(text) == expected


def test_reasons_are_bilingual_with_local_number_format(facts):
    v = verify(claim(ClaimType.DIVIDEND_YIELD, 9.5), facts)
    assert "9,26%" in v.reason.id and "9.26%" in v.reason.en
    v = verify(claim(ClaimType.MARKET_CAP, 250e12, "idr"), facts)
    assert "triliun" in v.reason.id and "trillion" in v.reason.en


@pytest.mark.parametrize("ctype,value,unit,direction", [
    (ClaimType.PROFIT_GROWTH, 20, "pct", "up"),
    (ClaimType.PROFIT_GROWTH, 30, "pct", "up"),
    (ClaimType.DIVIDEND_YIELD, 10.5, "pct", None),
    (ClaimType.MARKET_CAP, 250e12, "idr", None),
    (ClaimType.NET_INCOME, 7e12, "idr", None),
])
def test_bands_agree_with_label(facts, ctype, value, unit, direction):
    """The gauge draws ok_range/partial_range; they must tell the same story as the label."""
    v = verify(claim(ctype, value, unit, direction=direction), facts)
    in_ok = v.ok_range[0] <= value <= v.ok_range[1]
    in_partial = v.partial_range[0] <= value <= v.partial_range[1]
    assert (v.label == L.SESUAI) == in_ok
    assert (v.label == L.SEBAGIAN) == (in_partial and not in_ok)


def test_negative_idr_puts_sign_before_currency():
    from cekfakta.verify import fmt_idr
    assert fmt_idr(-16.74e12, "en") == "-Rp16.74 trillion"
    assert fmt_idr(-5e9, "id") == "-Rp5,00 miliar"
