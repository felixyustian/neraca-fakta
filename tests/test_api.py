"""API end to end on offline data: no Sectors key, no Anthropic key, no network."""
from __future__ import annotations

from fastapi.testclient import TestClient

from cekfakta import api
from cekfakta.config import Settings
from cekfakta.facts import FixtureSource
from cekfakta.pipeline import Checker


def client_for(fixture_dir, **overrides):
    settings = Settings(sectors_api_key="", sectors_base_url="", cache_path=fixture_dir / "c.sqlite",
                        credit_hard_cap=0, credit_offset=0, data_source="fixtures",
                        fixtures_dir=fixture_dir, **overrides)
    api.app.dependency_overrides[api.get_checker] = lambda: Checker(settings, FixtureSource(fixture_dir))
    return TestClient(api.app)


def test_health(fixture_dir):
    body = client_for(fixture_dir).get("/api/health").json()
    assert body["data_source"] == "fixtures" and body["llm_default"] == "rules"
    assert body["offline_tickers"] == ["TLKM"]
    assert [p["id"] for p in body["providers"]] == ["anthropic", "openai", "gemini"]
    assert not any(p["server_key"] for p in body["providers"])


def test_health_reports_server_keys_without_revealing_them(fixture_dir):
    r = client_for(fixture_dir, llm_keys={"gemini": "server-secret"}).get("/api/health")
    assert r.json()["llm_default"] == "gemini"
    assert "server-secret" not in r.text


def test_check_returns_verdicts(fixture_dir):
    r = client_for(fixture_dir).post("/api/check", json={"message": "TLKM laba naik 20% YoY, BBRI laba naik 50%"})
    assert r.status_code == 200
    body = r.json()
    labels = [(v["claim"]["ticker"], v["label"]) for v in body["verdicts"]]
    assert labels == [("TLKM", "Sesuai data"), ("BBRI", "Tidak dapat diverifikasi")]
    assert body["companies"][0]["name"] == "PT Contoh Tbk"
    assert body["credits_spent"] == 0
    assert any("BBRI" in n["id"] and "BBRI" in n["en"] for n in body["notes"])


def test_rejects_empty_and_oversized(fixture_dir):
    c = client_for(fixture_dir)
    assert c.post("/api/check", json={"message": ""}).status_code == 422
    assert c.post("/api/check", json={"message": "x" * 5000}).status_code == 422
