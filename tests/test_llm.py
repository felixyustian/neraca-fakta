"""Provider selection and per-request keys. LLM calls are stubbed: no network."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cekfakta import api
from cekfakta.config import Settings
from cekfakta.facts import FixtureSource
from cekfakta.llm import LLMError, LLMExtractor, _inline_refs, ExtractedClaims
from cekfakta.pipeline import Checker, LLMChoice, LLMConfigError
from cekfakta.schema import Claim, ClaimType


def settings(tmp_path, **kw):
    return Settings(sectors_api_key="", sectors_base_url="", cache_path=tmp_path / "c.sqlite",
                    credit_hard_cap=0, credit_offset=0, data_source="fixtures",
                    fixtures_dir=tmp_path, **kw)


@pytest.fixture
def stub_llm(monkeypatch):
    """Record which provider/key/model each extraction used; return one TLKM claim."""
    calls = []

    def fake_extract(self, message):
        calls.append((self.name, self._api_key, self.model))
        return [Claim(ticker="TLKM", claim_type=ClaimType.PROFIT_GROWTH, stated_value=20,
                      unit="pct", direction="up", source_text=message)]

    monkeypatch.setattr(LLMExtractor, "extract", fake_extract)
    return calls


@pytest.mark.parametrize("keys,provider,expected", [
    ({}, "", "rules"),
    ({"openai": "k"}, "", "openai"),
    ({"openai": "k", "anthropic": "k"}, "", "anthropic"),  # preference order
    ({"openai": "k", "anthropic": "k"}, "openai", "openai"),
    ({"openai": "k"}, "gemini", "openai"),  # configured provider has no key: next with one
    ({"openai": "k"}, "rules", "rules"),
])
def test_default_provider(tmp_path, keys, provider, expected):
    assert settings(tmp_path, llm_keys=keys, llm_provider=provider).default_llm_provider == expected


def test_user_key_overrides_server(tmp_path, stub_llm):
    c = Checker(settings(tmp_path, llm_keys={"anthropic": "server"}), FixtureSource(tmp_path))
    c.check("TLKM laba naik 20%", LLMChoice("gemini", "user-key", "gemini-x"))
    c.check("TLKM laba naik 20%", LLMChoice("anthropic"))
    assert stub_llm == [("gemini", "user-key", "gemini-x"), ("anthropic", "server", "claude-opus-5")]


def test_config_errors(tmp_path):
    c = Checker(settings(tmp_path, allow_user_keys=False), FixtureSource(tmp_path))
    with pytest.raises(LLMConfigError, match="tidak menerima"):
        c.extractor_for(LLMChoice("openai", "user-key"))
    with pytest.raises(LLMConfigError, match="Belum ada kunci"):
        c.extractor_for(LLMChoice("openai"))
    with pytest.raises(LLMConfigError, match="tidak dikenal"):
        c.extractor_for(LLMChoice("mistral", "k"))


def test_failed_call_falls_back_to_rules(tmp_path, monkeypatch):
    def boom(self, message):
        raise LLMError("auth", "401")

    monkeypatch.setattr(LLMExtractor, "extract", boom)
    c = Checker(settings(tmp_path), FixtureSource(tmp_path))
    r = c.check("TLKM laba naik 20% YoY", LLMChoice("openai", "bad-key"))
    assert r.extractor == "rules" and r.model is None
    assert r.verdicts[0].claim.claim_type == ClaimType.PROFIT_GROWTH
    assert "ditolak" in r.notes[0].id and "rejected" in r.notes[0].en


def test_api_headers(fixture_dir, stub_llm):
    s = settings(fixture_dir)
    api.app.dependency_overrides[api.get_checker] = lambda: Checker(s, FixtureSource(fixture_dir))
    client = TestClient(api.app)
    r = client.post("/api/check", json={"message": "TLKM laba naik 20%"},
                    headers={"X-LLM-Provider": "OpenAI", "X-LLM-Key": "sk-user"})
    assert r.status_code == 200
    assert (r.json()["extractor"], r.json()["model"]) == ("openai", "gpt-5-mini")
    assert "sk-user" not in r.text
    assert stub_llm[-1] == ("openai", "sk-user", "gpt-5-mini")

    r = client.post("/api/check", json={"message": "x"}, headers={"X-LLM-Provider": "gemini"})
    assert r.status_code == 400

    ok = client.post("/api/llm/test", headers={"X-LLM-Provider": "gemini", "X-LLM-Key": "k"}).json()
    assert ok == {"ok": True, "provider": "gemini", "model": "gemini-2.5-flash", "claims_found": 1}


def test_llm_test_endpoint_reports_bad_key(fixture_dir, monkeypatch):
    def boom(self, message):
        raise LLMError("auth", "401")

    monkeypatch.setattr(LLMExtractor, "extract", boom)
    s = settings(fixture_dir)
    api.app.dependency_overrides[api.get_checker] = lambda: Checker(s, FixtureSource(fixture_dir))
    body = TestClient(api.app).post("/api/llm/test", headers={"X-LLM-Provider": "anthropic",
                                                              "X-LLM-Key": "nope"}).json()
    assert body["ok"] is False and "ditolak" in body["error"]["id"]


def test_key_never_in_repr():
    assert "secret" not in repr(LLMChoice("openai", "secret"))


def test_gemini_schema_has_no_refs():
    assert "$ref" not in str(_inline_refs(ExtractedClaims.model_json_schema()))
