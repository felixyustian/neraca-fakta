"""Market side panels: IDX indices, movers, most traded, market cap, commodities, forex, news.

Sources
- Sectors API (IDX data, news, commodity prices). Cached in SQLite like every other call;
  IDX data changes once per trading day, so a full refresh (~12 credits) happens at most
  every few hours, and only while someone has the page open.
- Frankfurter (ECB reference rates, free, no key) for IDR exchange rates.

Budget: the panels use their own client with a credit reserve (MARKET_CREDIT_RESERVE,
default 100), so they stop fetching before they could starve fact-checks.
Offline mode reads snapshots saved by `scripts/probe_market.py` from fixtures/raw/market/.
Each section fails independently; the snapshot lists what's unavailable and why.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from .config import Settings
from .sectors_client import BudgetExceeded, SectorsClient, SectorsError
from .store import Store

log = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
# Everything the free ECB feed quotes that an Indonesian investor is likely to watch; the UI
# shows a default subset and lets viewers pick others.
FX_CURRENCIES = ["USD", "SGD", "EUR", "JPY", "CNY", "AUD", "GBP", "HKD", "MYR", "THB", "KRW", "CHF", "INR", "PHP"]
FX_TTL = 6 * 3600
# Listed first, in this order; any other index in the data follows alphabetically.
INDEX_CODES = ["LQ45", "IDX30", "IDX80", "KOMPAS100", "IDXHIDIV20", "JII70", "IDXBUMN20", "SRI-KEHATI"]
WATCHLIST_MAX = 5
IHSG_CODES = {"IHSG", "COMPOSITE", "JKSE"}
COMMODITIES = ["Coal", "Gold", "Copper"]
# The API field is named price_usd_per_ton for every commodity, but gold's values (~4,000)
# are clearly USD per troy ounce; per tonne would be ~130 million.
COMMODITY_UNITS = {"Gold": "USD/oz"}
NEWS_LIMIT = 15


# --- output models -------------------------------------------------------------

class Quote(BaseModel):
    code: str
    value: float
    change_pct: float | None = None
    date: str | None = None


class SeriesPoint(BaseModel):
    date: str
    value: float


class Mover(BaseModel):
    symbol: str
    name: str | None = None
    change_pct: float
    price: float | None = None


class Traded(BaseModel):
    symbol: str
    name: str | None = None
    volume: float
    price: float | None = None


class Commodity(BaseModel):
    name: str
    price: float
    unit: str
    change_pct: float | None = None
    date: str


class FxRate(BaseModel):
    currency: str
    rate: float  # IDR per 1 unit of currency
    change_pct: float | None = None
    date: str


class WatchQuote(BaseModel):
    symbol: str
    close: float | None = None
    change_pct: float | None = None
    date: str | None = None
    series: list[SeriesPoint] = []
    unavailable: str | None = None  # "not_found" | "budget" | "offline" | "error"


class NewsItem(BaseModel):
    title: str
    url: str
    source: str  # publisher domain, for attribution
    timestamp: str
    symbols: list[str] = []


class MarketSnapshot(BaseModel):
    data_source: Literal["live", "fixtures"]
    generated_at: str
    ihsg: Quote | None = None
    ihsg_series: list[SeriesPoint] = []
    indices: list[Quote] = []
    market_cap: Quote | None = None
    market_cap_series: list[SeriesPoint] = []
    gainers: list[Mover] = []
    losers: list[Mover] = []
    movers_date: str | None = None
    most_traded: list[Traded] = []
    most_traded_date: str | None = None
    commodities: list[Commodity] = []
    forex: list[FxRate] = []
    news: list[NewsItem] = []
    # section -> "budget" | "error" | "offline": shown by the UI instead of empty panels
    unavailable: dict[str, str] = {}


# --- raw data access -----------------------------------------------------------

def _strip_jk(symbol: str) -> str:
    return symbol.removesuffix(".JK")


def _pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or not prev:
        return None
    return (cur - prev) / abs(prev) * 100


class RawSource:
    """Named raw responses. Live calls the API (optionally recording to disk); fixtures replay."""

    def __init__(self, fetchers: dict[str, Callable[[], Any]] | None, fixtures_dir: Path,
                 record: bool = False):
        self.fetchers = fetchers  # None = fixtures mode
        self.dir = fixtures_dir
        self.record = record

    @property
    def live(self) -> bool:
        return self.fetchers is not None

    def get(self, name: str, fetch: Callable[[], Any] | None = None) -> Any:
        if not self.live:
            path = self.dir / f"{name}.json"
            if not path.exists():
                raise FileNotFoundError(name)
            return json.loads(path.read_text())
        body = (fetch or self.fetchers[name])()
        if self.record and body is not None:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False))
        return body


class MarketService:
    def __init__(self, settings: Settings, record: bool = False, dry_run: bool = False):
        self.settings = settings
        self.fixtures_dir = settings.fixtures_dir / "market"
        self.store = Store(settings.cache_path)
        self._lock = threading.Lock()
        live = settings.resolved_data_source == "live"
        self.client = (SectorsClient(settings=settings, reserve=settings.market_credit_reserve,
                                     dry_run=dry_run) if live else None)
        self.raw = RawSource({} if live else None, self.fixtures_dir, record=record)

    # Each section: returns normally, or raises; snapshot() records the failure.
    def snapshot(self) -> MarketSnapshot:
        with self._lock:
            snap = MarketSnapshot(
                data_source="live" if self.raw.live else "fixtures",
                generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            for section, fn in [
                ("indices", self._indices),
                ("market_cap", self._market_cap),
                ("movers", self._movers),
                ("most_traded", self._most_traded),
                ("commodities", self._commodities),
                ("news", self._news),
                ("forex", self._forex),
            ]:
                try:
                    fn(snap)
                except BudgetExceeded:
                    snap.unavailable[section] = "budget"
                except FileNotFoundError:
                    snap.unavailable[section] = "offline"
                except (SectorsError, httpx.HTTPError, KeyError, ValueError, TypeError, IndexError) as e:
                    log.warning("Market section %s failed: %s", section, e)
                    snap.unavailable[section] = "error"
            return snap

    # --- sections --------------------------------------------------------------
    def _indices(self, snap: MarketSnapshot) -> None:
        c = self.client
        today = date.today()
        hist = self.raw.get("ihsg_history", lambda: c.index_daily(
            "ihsg", (today - timedelta(days=45)).isoformat(), today.isoformat()))
        rows = sorted((r for r in hist or [] if r.get("price") is not None), key=lambda r: r["date"])
        if not rows:
            raise ValueError("no IHSG data")
        snap.ihsg_series = [SeriesPoint(date=r["date"], value=r["price"]) for r in rows[-30:]]
        last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
        snap.ihsg = Quote(code="IHSG", value=last["price"], date=last["date"],
                          change_pct=_pct_change(last["price"], prev and prev["price"]))

        latest = self.raw.get("indices_latest", lambda: c.index_daily_universe(last["date"]))
        previous = (self.raw.get("indices_prev", lambda: c.index_daily_universe(prev["date"], historical=True))
                    if prev else [])
        prev_by_code = {r["index_code"].upper(): r["price"] for r in previous or []}
        by_code = {r["index_code"].upper(): r for r in latest or []}
        order = [c for c in INDEX_CODES if c in by_code] + sorted(set(by_code) - set(INDEX_CODES))
        snap.indices = [
            Quote(code=code, value=by_code[code]["price"], date=by_code[code].get("date"),
                  change_pct=_pct_change(by_code[code]["price"], prev_by_code.get(code)))
            for code in order if code not in IHSG_CODES
        ]

    def _market_cap(self, snap: MarketSnapshot) -> None:
        rows = self.raw.get("idx_total", lambda: self.client.idx_total())
        rows = sorted((r for r in rows or [] if r.get("idx_total_market_cap")), key=lambda r: r["date"])
        if not rows:
            raise ValueError("no market cap data")
        snap.market_cap_series = [SeriesPoint(date=r["date"], value=r["idx_total_market_cap"]) for r in rows]
        last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
        snap.market_cap = Quote(code="IDX", value=last["idx_total_market_cap"], date=last["date"],
                                change_pct=_pct_change(last["idx_total_market_cap"],
                                                       prev and prev["idx_total_market_cap"]))

    def _movers(self, snap: MarketSnapshot) -> None:
        for cls, attr in (("top_gainers", "gainers"), ("top_losers", "losers")):
            body = self.raw.get(cls, lambda cls=cls: self.client.top_changes(cls, "1d", 5))
            rows = (body or {}).get(cls, {}).get("1d", [])
            setattr(snap, attr, [
                Mover(symbol=_strip_jk(r["symbol"]), name=r.get("name"),
                      change_pct=r["price_change"] * 100, price=r.get("last_close_price"))
                for r in rows if r.get("price_change") is not None
            ])
            if rows and not snap.movers_date:
                snap.movers_date = rows[0].get("latest_close_date")

    def _most_traded(self, snap: MarketSnapshot) -> None:
        today = date.today()
        body = self.raw.get("most_traded", lambda: self.client.most_traded(
            (today - timedelta(days=7)).isoformat(), today.isoformat(), 5))
        if not body:
            raise ValueError("no most-traded data")
        day = max(body)
        snap.most_traded_date = day
        snap.most_traded = [
            Traded(symbol=_strip_jk(r["symbol"]), name=r.get("company_name"), volume=r["volume"], price=r.get("price"))
            for r in body[day]
        ]

    def _commodities(self, snap: MarketSnapshot) -> None:
        start = date.today().year - 1
        out = []
        missing = 0
        for name in COMMODITIES:
            try:
                rows = self.raw.get(f"commodity_{name.lower()}", lambda name=name: self.client.commodity_price(name, start))
            except FileNotFoundError:  # one missing snapshot shouldn't hide the others
                missing += 1
                continue
            rows = sorted((r for r in rows or [] if r.get("price_usd_per_ton") is not None), key=lambda r: r["date"])
            if not rows:
                continue
            last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
            out.append(Commodity(name=name, price=last["price_usd_per_ton"], unit=COMMODITY_UNITS.get(name, "USD/t"),
                                 date=last["date"],
                                 change_pct=_pct_change(last["price_usd_per_ton"], prev and prev["price_usd_per_ton"])))
        if not out:
            if missing == len(COMMODITIES):
                raise FileNotFoundError("commodities")
            raise ValueError("no commodity data")
        snap.commodities = out

    def _news(self, snap: MarketSnapshot) -> None:
        body = self.raw.get("news", lambda: self.client.news(NEWS_LIMIT))
        items = []
        for r in (body or {}).get("results", []):
            url = r.get("source") or ""
            if not r.get("title") or not url.startswith(("http://", "https://")):
                continue
            items.append(NewsItem(
                title=r["title"].strip(), url=url, timestamp=r.get("timestamp") or "",
                source=urlparse(url).netloc.removeprefix("www."),
                symbols=[_strip_jk(s) for s in r.get("symbols") or []][:4],
            ))
        snap.news = sorted(items, key=lambda n: n.timestamp, reverse=True)

    def _forex(self, snap: MarketSnapshot) -> None:
        """IDR per unit of each currency, latest ECB fixing vs the previous one.

        Uses the ECB's native EUR base and crosses the rates: IDR-based quotes are rounded to a
        few significant digits (1 IDR = 0.000056 USD), which would put USD/IDR off by ~60.
        """
        end = date.today()
        path = f"{FRANKFURTER_URL}/{(end - timedelta(days=10)).isoformat()}.."
        params = {"base": "EUR", "symbols": ",".join(["IDR"] + [c for c in FX_CURRENCIES if c != "EUR"])}

        def fetch() -> Any:
            cached = self.store.get(path, params, FX_TTL)
            if cached is not None:
                return cached[1]
            resp = httpx.get(path, params=params, timeout=8.0)
            resp.raise_for_status()
            body = resp.json()
            self.store.put(path, params, resp.status_code, body)
            return body

        try:
            body = fetch() if self.raw.live else None
        except httpx.HTTPError:
            body = None
        if body is None:  # offline mode, or the free API is down: fall back to the saved snapshot
            body = RawSource(None, self.fixtures_dir).get("forex")
        elif self.raw.record:
            self.fixtures_dir.mkdir(parents=True, exist_ok=True)
            (self.fixtures_dir / "forex.json").write_text(json.dumps(body, indent=2))
        days = sorted(body["rates"])

        def idr_per(day: dict[str, float], cur: str) -> float | None:
            if not day.get("IDR"):
                return None
            return day["IDR"] if cur == "EUR" else (day["IDR"] / day[cur] if day.get(cur) else None)

        last, prev = body["rates"][days[-1]], body["rates"][days[-2]] if len(days) > 1 else {}
        snap.forex = [
            FxRate(currency=cur, rate=rate, date=days[-1], change_pct=_pct_change(rate, idr_per(prev, cur)))
            for cur in FX_CURRENCIES if (rate := idr_per(last, cur)) is not None
        ]

    # --- watchlist ---------------------------------------------------------------
    def watchlist(self, symbols: list[str]) -> list[WatchQuote]:
        """Latest close, daily change and ~30 closes per symbol (1 credit per new symbol, cached 6h)."""
        from .facts import DAILY_WINDOW_DAYS, FixtureSource
        from .sectors_client import normalize_symbol

        out = []
        for raw in symbols[:WATCHLIST_MAX]:
            try:
                sym = normalize_symbol(raw)
            except ValueError:
                continue
            q = WatchQuote(symbol=sym)
            try:
                if self.client is None:
                    rows = FixtureSource(self.settings.fixtures_dir).daily(sym)
                else:
                    end = date.today()
                    rows = self.client.daily(sym, (end - timedelta(days=DAILY_WINDOW_DAYS)).isoformat(),
                                             end.isoformat()) or []
                rows = sorted((r for r in rows if r.get("close") is not None), key=lambda r: r["date"])
                if not rows:
                    raise ValueError("no prices")
                last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
                q.close, q.date = last["close"], last["date"]
                q.change_pct = _pct_change(last["close"], prev and prev["close"])
                q.series = [SeriesPoint(date=r["date"], value=r["close"]) for r in rows[-30:]]
            except BudgetExceeded:
                q.unavailable = "budget"
            except SectorsError as e:
                q.unavailable = "not_found" if e.status == 404 else "error"
            except LookupError:  # TickerNotFound from the fixture source
                q.unavailable = "offline"
            except (httpx.HTTPError, ValueError, KeyError) as e:
                log.warning("Watchlist %s failed: %s", sym, e)
                q.unavailable = "error"
            out.append(q)
        return out
