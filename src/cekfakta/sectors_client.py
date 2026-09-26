"""Thin client for the Sectors Financial API v2 (IDX only).

Design rules:
- Every response is cached in SQLite; a cache hit costs 0 credits.
- Every paid call is written to a local credit ledger using the documented
  billing rules (2xx = endpoint cost, 404 = 1 credit, other errors = free).
- A hard cap refuses paid calls before the budget runs out.

Documented costs (docs.sectors.app, checked 26 Sep 2026):
- /v2/company/report/{symbol}/       1 credit per requested section
- /v2/financials/quarterly/{symbol}/ 1 credit per quarter returned
- /v2/daily/{symbol}/                1 credit
Market panels (checked 26 Sep 2026):
- /v2/index-daily/                   1 credit (every index, one date)
- /v2/index-daily/{code}/            1 credit (one index, up to 90 days)
- /v2/companies/top-changes/         1 credit per classification x period
- /v2/most-traded/                   2 credits
- /v2/idx-total/                     1 credit
- /v2/news/                          1 credit
- /v2/mining/commodities/{name}/price/ 1 credit
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

from .config import Settings, load_settings
from .store import Store

REPORT_SECTIONS = {
    "overview", "valuation", "future", "peers",
    "financials", "dividend", "management", "ownership",
}

# Cache lifetimes, in seconds.
TTL_REPORT = 12 * 3600
TTL_QUARTERLY = 7 * 24 * 3600
TTL_DAILY = 6 * 3600
# IDX market data changes once per trading day; news more often.
TTL_MARKET = 6 * 3600
TTL_HISTORY = 30 * 24 * 3600  # a past date's close never changes
TTL_NEWS = 3600
TTL_COMMODITY = 24 * 3600

_SYMBOL_RE = re.compile(r"^[A-Z]{4}$")


class SectorsError(RuntimeError):
    def __init__(self, status: int, body: Any, path: str):
        super().__init__(f"Sectors API {status} on {path}: {body}")
        self.status = status
        self.body = body
        self.path = path


class BudgetExceeded(RuntimeError):
    pass


def normalize_symbol(raw: str) -> str:
    """'bbca', 'BBCA.JK', ' $BBCA ' -> 'BBCA'. Raises ValueError if not a 4-letter IDX code."""
    s = raw.strip().upper().lstrip("$")
    if s.endswith(".JK"):
        s = s[:-3]
    if not _SYMBOL_RE.match(s):
        raise ValueError(f"Not a valid IDX symbol: {raw!r}")
    return s


@dataclass
class PlannedCall:
    path: str
    params: dict[str, Any]
    est_credits: int


@dataclass
class SectorsClient:
    settings: Settings = field(default_factory=load_settings)
    transport: httpx.BaseTransport | None = None  # injectable for tests
    dry_run: bool = False
    planned: list[PlannedCall] = field(default_factory=list)
    # Credits this client must leave untouched under the cap (market panels keep a reserve
    # so they can never starve fact-checks).
    reserve: int = 0

    def __post_init__(self) -> None:
        self.store = Store(self.settings.cache_path)
        if not self.dry_run and not self.settings.sectors_api_key:
            raise RuntimeError("SECTORS_API_KEY is not set. Copy .env.example to .env and add your key.")
        self._http = httpx.Client(
            base_url=self.settings.sectors_base_url,
            headers={"Authorization": self.settings.sectors_api_key},  # raw key, not "Bearer"
            timeout=30.0,
            transport=self.transport,
        )

    # --- budget ------------------------------------------------------------
    @property
    def credits_spent(self) -> int:
        return self.store.credits_spent() + self.settings.credit_offset

    @property
    def credits_remaining_under_cap(self) -> int:
        return self.settings.credit_hard_cap - self.credits_spent

    # --- core request --------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any], est_credits: int, ttl: float,
             actual_cost: callable) -> Any:
        cached = self.store.get(path, params, ttl)
        if cached is not None:
            status, body = cached
            if status >= 400:
                raise SectorsError(status, body, path)
            return body

        if self.dry_run:
            self.planned.append(PlannedCall(path, params, est_credits))
            return None

        if est_credits > self.credits_remaining_under_cap - self.reserve:
            raise BudgetExceeded(
                f"Call to {path} would cost ~{est_credits} credits; "
                f"only {self.credits_remaining_under_cap} left under the cap"
                + (f" (reserve {self.reserve})." if self.reserve else ".")
            )

        resp = self._http.get(path, params=params)
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:500]}

        status = resp.status_code
        if 200 <= status < 300:
            credits = actual_cost(body)
        elif status == 404:
            credits = 1
        else:
            credits = 0
        if credits:
            self.store.record_spend(path, params, status, credits)

        # Cache successes and 404s (a missing symbol stays missing; don't pay twice).
        if 200 <= status < 300 or status == 404:
            self.store.put(path, params, status, body)
        if status >= 400:
            raise SectorsError(status, body, path)
        return body

    # --- endpoints -----------------------------------------------------------
    def company_report(self, symbol: str, sections: Iterable[str]) -> Any:
        sym = normalize_symbol(symbol)
        secs = sorted(set(sections))
        unknown = set(secs) - REPORT_SECTIONS
        if unknown or not secs:
            raise ValueError(f"Invalid sections: {unknown or 'none given'}")
        return self._get(
            f"/v2/company/report/{sym}/",
            {"sections": ",".join(secs)},
            est_credits=len(secs),
            ttl=TTL_REPORT,
            actual_cost=lambda _body: len(secs),
        )

    def quarterly_financials(self, symbol: str, n_quarters: int = 1) -> Any:
        sym = normalize_symbol(symbol)
        if n_quarters < 1:
            raise ValueError("n_quarters must be >= 1")
        return self._get(
            f"/v2/financials/quarterly/{sym}/",
            {"n_quarters": n_quarters},
            est_credits=n_quarters,
            ttl=TTL_QUARTERLY,
            actual_cost=lambda body: max(1, len(body)) if isinstance(body, list) else 1,
        )

    def daily(self, symbol: str, start: str | None = None, end: str | None = None) -> Any:
        sym = normalize_symbol(symbol)
        params = {k: v for k, v in {"start": start, "end": end}.items() if v}
        return self._get(
            f"/v2/daily/{sym}/",
            params,
            est_credits=1,
            ttl=TTL_DAILY,
            actual_cost=lambda _body: 1,
        )

    # --- market panels ------------------------------------------------------------
    def index_daily(self, code: str, start: str | None = None, end: str | None = None) -> Any:
        params = {k: v for k, v in {"start": start, "end": end}.items() if v}
        return self._get(f"/v2/index-daily/{code.lower()}/", params, est_credits=1, ttl=TTL_MARKET,
                         actual_cost=lambda _b: 1)

    def index_daily_universe(self, date: str | None = None, historical: bool = False) -> Any:
        return self._get("/v2/index-daily/", {"date": date} if date else {}, est_credits=1,
                         ttl=TTL_HISTORY if historical else TTL_MARKET, actual_cost=lambda _b: 1)

    def top_changes(self, classification: str, period: str = "1d", n_stock: int = 5) -> Any:
        """One classification x period per call: unambiguous params, exactly 1 credit."""
        if classification not in ("top_gainers", "top_losers"):
            raise ValueError(f"Invalid classification {classification!r}")
        params = {"classifications": classification, "periods": period, "n_stock": n_stock}
        return self._get("/v2/companies/top-changes/", params, est_credits=1, ttl=TTL_MARKET,
                         actual_cost=lambda _b: 1)

    def most_traded(self, start: str | None = None, end: str | None = None, n_stock: int = 5) -> Any:
        params = {k: v for k, v in {"start": start, "end": end, "n_stock": n_stock}.items() if v}
        return self._get("/v2/most-traded/", params, est_credits=2, ttl=TTL_MARKET,
                         actual_cost=lambda _b: 2)

    def idx_total(self, start: str | None = None, end: str | None = None) -> Any:
        params = {k: v for k, v in {"start": start, "end": end}.items() if v}
        return self._get("/v2/idx-total/", params, est_credits=1, ttl=TTL_MARKET, actual_cost=lambda _b: 1)

    def news(self, limit: int = 20) -> Any:
        return self._get("/v2/news/", {"limit": limit}, est_credits=1, ttl=TTL_NEWS, actual_cost=lambda _b: 1)

    def commodity_price(self, name: str, start_year: int | None = None) -> Any:
        params = {"start_year": start_year} if start_year else {}
        return self._get(f"/v2/mining/commodities/{name.lower()}/price/", params, est_credits=1,
                         ttl=TTL_COMMODITY, actual_cost=lambda _b: 1)
