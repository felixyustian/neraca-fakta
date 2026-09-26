"""Market panels: parsing, per-section failure, credit reserve. No network."""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from cekfakta.config import Settings
from cekfakta.market import MarketService
from cekfakta.sectors_client import BudgetExceeded, SectorsClient

FX = {"rates": {
    "2026-09-24": {"IDR": 20000.0, "USD": 1.10, "SGD": 1.45, "JPY": 180.0, "CNY": 7.8, "AUD": 1.6},
    "2026-09-25": {"IDR": 20400.0, "USD": 1.12, "SGD": 1.45, "JPY": 180.0, "CNY": 7.8, "AUD": 1.6},
}}


def settings(tmp_path, **kw):
    return Settings(sectors_api_key="", sectors_base_url="https://api.sectors.app",
                    cache_path=tmp_path / "c.sqlite", credit_hard_cap=950, credit_offset=0,
                    data_source="fixtures", fixtures_dir=tmp_path, **kw)


def write(tmp_path, name, body):
    d = tmp_path / "market"
    d.mkdir(exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(body))


def test_fixture_snapshot_parses_every_section(tmp_path):
    write(tmp_path, "ihsg_history", [{"index_code": "IHSG", "date": "2026-09-24", "price": 6300},
                                     {"index_code": "IHSG", "date": "2026-09-25", "price": 6237}])
    write(tmp_path, "indices_latest", [{"index_code": "LQ45", "date": "2026-09-25", "price": 621}])
    write(tmp_path, "indices_prev", [{"index_code": "LQ45", "date": "2026-09-24", "price": 623}])
    write(tmp_path, "top_gainers", {"top_gainers": {"1d": [{"symbol": "PACK.JK", "name": "X", "price_change": 0.066,
                                                            "last_close_price": 645, "latest_close_date": "2026-09-25"}]}})
    write(tmp_path, "top_losers", {"top_losers": {"1d": []}})
    write(tmp_path, "commodity_gold", [{"name": "Gold", "date": "2026-08-01", "price_usd_per_ton": 4000},
                                       {"name": "Gold", "date": "2026-09-01", "price_usd_per_ton": 4400}])
    write(tmp_path, "news", {"results": [
        {"title": "Old", "source": "https://www.kontan.co.id/a", "timestamp": "2026-09-25T08:00:00", "symbols": []},
        {"title": "New", "source": "https://investor.id/b", "timestamp": "2026-09-26T10:15:00", "symbols": ["GOTO.JK"]},
        {"title": "No link", "source": "", "timestamp": "2026-09-26T11:00:00"},
    ]})
    write(tmp_path, "forex", FX)

    snap = MarketService(settings(tmp_path)).snapshot()
    assert snap.ihsg.code == "IHSG" and snap.ihsg.change_pct == pytest.approx(-1.0)
    assert [(q.code, round(q.change_pct, 2)) for q in snap.indices] == [("LQ45", -0.32)]
    assert snap.gainers[0].symbol == "PACK" and snap.gainers[0].change_pct == pytest.approx(6.6)
    assert snap.commodities[0].unit == "USD/oz" and snap.commodities[0].change_pct == pytest.approx(10)
    assert [n.title for n in snap.news] == ["New", "Old"]  # newest first, unlinked items dropped
    assert snap.news[0].source == "investor.id" and snap.news[0].symbols == ["GOTO"]
    usd = next(f for f in snap.forex if f.currency == "USD")
    assert usd.rate == pytest.approx(20400 / 1.12)  # crossed through EUR, not inverted IDR quotes
    assert next(f for f in snap.forex if f.currency == "EUR").rate == 20400
    # Missing fixtures are reported, not fatal.
    assert snap.unavailable == {"market_cap": "offline", "most_traded": "offline"}


def test_reserve_blocks_panel_calls_but_not_checks(tmp_path):
    s = replace(settings(tmp_path), sectors_api_key="k", credit_hard_cap=100)
    calls = []
    transport = httpx.MockTransport(lambda req: calls.append(1) or httpx.Response(200, json=[]))
    panels = SectorsClient(settings=s, transport=transport, reserve=100)
    with pytest.raises(BudgetExceeded):
        panels.idx_total()
    SectorsClient(settings=s, transport=transport).idx_total()  # a normal client still may spend
    assert calls == [1]


def test_budget_shows_as_unavailable(tmp_path, monkeypatch):
    s = replace(settings(tmp_path), sectors_api_key="k", data_source="live", credit_hard_cap=50,
                market_credit_reserve=100)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    write(tmp_path, "forex", FX)
    snap = MarketService(s).snapshot()
    assert snap.unavailable["indices"] == "budget" and snap.unavailable["news"] == "budget"
    assert snap.forex  # the free forex source fell back to the saved snapshot


def test_watchlist_offline_uses_daily_fixtures(tmp_path):
    (tmp_path / "TLKM_daily.json").write_text(json.dumps([
        {"date": "2026-09-24", "close": 2400}, {"date": "2026-09-25", "close": 2460}]))
    svc = MarketService(settings(tmp_path))
    tlkm, zzzz, = svc.watchlist(["tlkm", "ZZZZ", "not-a-code"])  # invalid codes are dropped
    assert (tlkm.symbol, tlkm.close, round(tlkm.change_pct, 2)) == ("TLKM", 2460, 2.5)
    assert len(tlkm.series) == 2
    assert zzzz.unavailable == "offline"
    assert len(svc.watchlist(["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII"])) == 5  # capped


def test_watchlist_live_404_is_not_found(tmp_path):
    s = replace(settings(tmp_path), sectors_api_key="k", data_source="live")
    svc = MarketService(s)
    svc.client = SectorsClient(settings=s, reserve=0, transport=httpx.MockTransport(
        lambda req: httpx.Response(404, json={"error": "Given stock symbol does not exist."})))
    [q] = svc.watchlist(["ZZZZ"])
    assert q.unavailable == "not_found"
