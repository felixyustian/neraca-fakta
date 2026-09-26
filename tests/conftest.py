"""Shared test data: small synthetic Sectors-shaped responses (real ones are git-ignored)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPORT = {
    "symbol": "TEST.JK",
    "company_name": "PT Contoh Tbk",
    "overview": {"sector": "Infrastructures", "market_cap": 240_000_000_000_000,
                 "last_close_price": 2400, "latest_close_date": "2026-09-25"},
    "financials": {
        "yoy_quarter_revenue_growth": 0.064,
        "yoy_quarter_earnings_growth": 0.216,
        "historical_financials": [{"year": 2025, "earnings": 17_800_000_000_000}],
    },
    "dividend": {"yield_ttm": 0.0926},
}
QUARTERS = [
    {"date": "2026-06-30", "revenue": 38_689_000_000_000, "earnings": 6_279_000_000_000},
    {"date": "2026-03-31", "revenue": 37_189_000_000_000, "earnings": 4_344_000_000_000},
]


@pytest.fixture
def facts():
    from cekfakta.facts import CompanyFacts
    return CompanyFacts(ticker="TLKM", report=REPORT, quarters=QUARTERS)


@pytest.fixture
def fixture_dir(tmp_path):
    (tmp_path / "TLKM_report.json").write_text(json.dumps(REPORT))
    (tmp_path / "TLKM_quarterly.json").write_text(json.dumps(QUARTERS))
    return tmp_path
