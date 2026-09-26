"""Company facts the verifier compares claims against, from live Sectors data or local fixtures.

Per new ticker a check fetches the report (overview, financials, dividend: 3 credits), the
last two quarters (2 credits), and ~90 days of daily prices for the chart (1 credit).
Everything is cached, so a repeat check costs 0.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol

from .config import Settings
from .schema import (AnnualPoint, CompanySnapshot, DividendPoint, PriceMark, PricePoint,
                     QuarterPoint)
from .sectors_client import SectorsClient, SectorsError

REPORT_SECTIONS = ["overview", "financials", "dividend"]
DAILY_WINDOW_DAYS = 89  # the API's maximum window is 90 days
CHART_YEARS = 6


class TickerNotFound(LookupError):
    pass


class DataSource(Protocol):
    name: str

    def report(self, symbol: str) -> dict[str, Any]: ...
    def quarterly(self, symbol: str) -> list[dict[str, Any]]: ...
    def daily(self, symbol: str) -> list[dict[str, Any]]: ...
    def credits_spent(self) -> int: ...


class LiveSource:
    name = "live"

    def __init__(self, client: SectorsClient):
        self.client = client

    def report(self, symbol: str) -> dict[str, Any]:
        try:
            return self.client.company_report(symbol, REPORT_SECTIONS)
        except SectorsError as e:
            if e.status == 404:
                raise TickerNotFound(symbol) from e
            raise

    def quarterly(self, symbol: str) -> list[dict[str, Any]]:
        try:
            return self.client.quarterly_financials(symbol, 2) or []
        except SectorsError as e:
            if e.status == 404:
                raise TickerNotFound(symbol) from e
            raise

    def daily(self, symbol: str) -> list[dict[str, Any]]:
        end = date.today()
        start = end - timedelta(days=DAILY_WINDOW_DAYS)
        try:
            return self.client.daily(symbol, start.isoformat(), end.isoformat()) or []
        except SectorsError as e:
            if e.status == 404:
                raise TickerNotFound(symbol) from e
            raise

    def credits_spent(self) -> int:
        return self.client.credits_spent


class FixtureSource:
    """Offline mode: reads responses saved by scripts/probe.py. Costs nothing."""
    name = "fixtures"

    def __init__(self, directory: Path):
        self.directory = directory

    def _load(self, symbol: str, kind: str) -> Any:
        path = self.directory / f"{symbol}_{kind}.json"
        if not path.exists():
            raise TickerNotFound(symbol)
        return json.loads(path.read_text())

    def report(self, symbol: str) -> dict[str, Any]:
        return self._load(symbol, "report")

    def quarterly(self, symbol: str) -> list[dict[str, Any]]:
        return self._load(symbol, "quarterly")

    def daily(self, symbol: str) -> list[dict[str, Any]]:
        return self._load(symbol, "daily")

    def available(self) -> list[str]:
        return sorted(p.name.split("_")[0] for p in self.directory.glob("*_report.json"))

    def credits_spent(self) -> int:
        return 0


def make_source(settings: Settings) -> DataSource:
    if settings.resolved_data_source == "live":
        return LiveSource(SectorsClient(settings=settings))
    return FixtureSource(settings.fixtures_dir)


@dataclass
class CompanyFacts:
    """Numbers normalized to the units claims use: growth and yield in percent, money in IDR."""
    ticker: str
    report: dict[str, Any]
    quarters: list[dict[str, Any]] | None = None  # newest first; None = not fetched
    daily: list[dict[str, Any]] | None = None     # oldest first; chart only, never verified against

    def _section(self, name: str) -> dict[str, Any]:
        return self.report.get(name) or {}

    @staticmethod
    def _pct(x: float | None) -> float | None:
        return None if x is None else x * 100

    @property
    def yoy_revenue_growth_pct(self) -> float | None:
        return self._pct(self._section("financials").get("yoy_quarter_revenue_growth"))

    @property
    def yoy_earnings_growth_pct(self) -> float | None:
        return self._pct(self._section("financials").get("yoy_quarter_earnings_growth"))

    @property
    def dividend_yield_pct(self) -> float | None:
        return self._pct(self._section("dividend").get("yield_ttm"))

    @property
    def market_cap(self) -> float | None:
        return self._section("overview").get("market_cap")

    def quarter(self, i: int) -> dict[str, Any] | None:
        if not self.quarters or len(self.quarters) <= i:
            return None
        return self.quarters[i]

    def qoq_growth_pct(self, field: str) -> float | None:
        cur, prev = self.quarter(0), self.quarter(1)
        if not cur or not prev or not prev.get(field) or cur.get(field) is None:
            return None
        return (cur[field] - prev[field]) / abs(prev[field]) * 100

    def snapshot(self) -> CompanySnapshot:
        ov = self._section("overview")
        fin = self._section("financials")
        div = self._section("dividend")
        q0 = self.quarter(0)
        return CompanySnapshot(
            ticker=self.ticker,
            name=self.report.get("company_name"),
            sector=ov.get("sector"),
            sub_sector=ov.get("sub_sector"),
            last_close_price=ov.get("last_close_price"),
            latest_close_date=ov.get("latest_close_date"),
            daily_change_pct=self._pct(ov.get("daily_close_change")),
            market_cap=ov.get("market_cap"),
            market_cap_rank=ov.get("market_cap_rank"),
            latest_quarter=q0.get("date") if q0 else None,
            yoy_revenue_growth_pct=self.yoy_revenue_growth_pct,
            yoy_earnings_growth_pct=self.yoy_earnings_growth_pct,
            dividend_yield_pct=self.dividend_yield_pct,
            eps=fin.get("eps"),
            high_52w=_mark((ov.get("all_time_price") or {}).get("52_w_high")),
            low_52w=_mark((ov.get("all_time_price") or {}).get("52_w_low")),
            all_time_high=_mark((ov.get("all_time_price") or {}).get("all_time_high")),
            annual=[
                AnnualPoint(year=r["year"], revenue=r.get("revenue"), earnings=r.get("earnings"))
                for r in sorted(fin.get("historical_financials") or [], key=lambda r: r["year"])
                if r.get("revenue") is not None or r.get("earnings") is not None
            ][-CHART_YEARS:],
            quarters=[
                QuarterPoint(date=q["date"], revenue=q.get("revenue"), earnings=q.get("earnings"))
                for q in reversed(self.quarters or [])
            ],
            dividends=[
                DividendPoint(year=int(y), total=v.get("total_dividend"),
                              yield_pct=self._pct(v.get("total_yield")))
                for y, v in sorted((div.get("historical_dividends") or {}).items())
            ][-CHART_YEARS:],
            prices=[PricePoint(date=d["date"], close=d["close"])
                    for d in (self.daily or []) if d.get("close") is not None],
        )


def _mark(entry: dict[str, float] | None) -> PriceMark | None:
    """Sectors encodes a dated price as {"2026-01-27": 3990}."""
    if not entry:
        return None
    (d, price), = entry.items()
    return PriceMark(date=d, price=price)
