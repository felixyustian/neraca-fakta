"""Client tests with a mocked transport. No network, no credits spent."""
from __future__ import annotations

import httpx
import pytest

from cekfakta.config import Settings
from cekfakta.sectors_client import (
    BudgetExceeded,
    SectorsClient,
    SectorsError,
    normalize_symbol,
)


def make_client(tmp_path, handler, cap=950):
    settings = Settings(
        sectors_api_key="test-key",
        sectors_base_url="https://api.sectors.app",
        cache_path=tmp_path / "cache.sqlite",
        credit_hard_cap=cap,
        credit_offset=0,
    )
    return SectorsClient(settings=settings, transport=httpx.MockTransport(handler))


def test_auth_header_is_raw_key(tmp_path):
    seen = {}

    def handler(req):
        seen["auth"] = req.headers.get("Authorization")
        return httpx.Response(200, json=[{"close": 1}])

    make_client(tmp_path, handler).daily("BBCA")
    assert seen["auth"] == "test-key"


def test_report_costs_one_credit_per_section_and_caches(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"symbol": "BBCA.JK", "overview": {}})

    c = make_client(tmp_path, handler)
    c.company_report("bbca.jk", ["overview", "financials", "dividend"])
    c.company_report("BBCA", ["dividend", "overview", "financials"])  # same set, other order
    assert len(calls) == 1
    assert c.credits_spent == 3


def test_quarterly_cost_equals_quarters_returned(tmp_path):
    c = make_client(tmp_path, lambda req: httpx.Response(200, json=[{"date": "2026-06-30"}]))
    c.quarterly_financials("TLKM", n_quarters=4)  # asked 4, API returned 1
    assert c.credits_spent == 1


def test_404_costs_one_credit_and_is_cached(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404, json={"error": "Given stock symbol does not exist."})

    c = make_client(tmp_path, handler)
    for _ in range(2):
        with pytest.raises(SectorsError):
            c.daily("ZZZZ")
    assert len(calls) == 1
    assert c.credits_spent == 1


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_other_errors_are_free(tmp_path, status):
    c = make_client(tmp_path, lambda req: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(SectorsError):
        c.daily("BBCA")
    assert c.credits_spent == 0


def test_budget_cap_blocks_before_calling(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={})

    c = make_client(tmp_path, handler, cap=2)
    with pytest.raises(BudgetExceeded):
        c.company_report("BBCA", ["overview", "financials", "dividend"])
    assert calls == []


@pytest.mark.parametrize("raw,expected", [("bbca", "BBCA"), ("BBCA.JK", "BBCA"), (" $tlkm ", "TLKM")])
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["BCA", "BBCAX", "12AB", ""])
def test_normalize_symbol_rejects(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)
