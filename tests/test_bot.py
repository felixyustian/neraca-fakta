"""Chat bots: core behaviour, Telegram adapter, WhatsApp webhook. All network is mocked."""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from cekfakta import api
from cekfakta.bot import whatsapp
from cekfakta.bot.core import ChatBot
from cekfakta.bot.markup import TelegramHTML, WhatsAppText, split_message
from cekfakta.bot.telegram import TelegramBot
from cekfakta.config import Settings
from cekfakta.facts import FixtureSource
from cekfakta.pipeline import Checker
from cekfakta.store import Store


def settings(tmp_path, **kw):
    return Settings(sectors_api_key="", sectors_base_url="", cache_path=tmp_path / "c.sqlite",
                    credit_hard_cap=0, credit_offset=0, data_source="fixtures", fixtures_dir=tmp_path,
                    market_panels=False, **kw)


@pytest.fixture
def bot(fixture_dir):
    s = settings(fixture_dir)
    store = Store(s.cache_path)
    return ChatBot(Checker(s, FixtureSource(fixture_dir)), store, checks_per_hour=3, app_url="https://app.example")


# --- core ------------------------------------------------------------------------

def test_check_reply_has_verdict_numbers_and_link(bot):
    [reply] = bot.handle("tg:1", "TLKM laba naik 20% YoY", TelegramHTML())
    assert "✅ <b>TLKM · Pertumbuhan laba</b> — Sesuai data" in reply
    assert "Klaim +20,0%, data +21,6% (Q2 2026" in reply
    assert "Skor kesesuaian 100/100" in reply
    assert '<a href="https://app.example">' in reply


def test_user_text_is_escaped(bot):
    [reply] = bot.handle("tg:1", "TLKM laba naik 20% <script>x</script>", TelegramHTML())
    assert "<script>" not in reply and "&lt;script&gt;" in reply


def test_language_switch_persists_per_chat(bot):
    assert bot.handle("tg:1", "/lang en", TelegramHTML()) == ["Language set to English."]
    [reply] = bot.handle("tg:1", "TLKM laba naik 20% YoY", TelegramHTML())
    assert "Matches data" in reply and "Claimed +20.0%, data +21.6%" in reply
    assert "Sesuai data" in bot.handle("tg:2", "TLKM laba naik 20% YoY", TelegramHTML())[0]


def test_commands_and_edge_cases(bot):
    assert "Neraca Fakta" in bot.handle("wa:1", "help", WhatsAppText())[0]
    assert "Fact Ledger" in bot.handle("tg:9", "/start", TelegramHTML(), lang_hint="en-US")[0]
    assert "tidak tersedia" in bot.handle("tg:1", "/pasar", TelegramHTML())[0]  # panels off here
    assert "Tidak ada klaim" in bot.handle("tg:1", "halo semua apa kabar", TelegramHTML())[0]
    assert "terlalu panjang" in bot.handle("tg:1", "x" * 5000, TelegramHTML())[0]
    assert "/cek" in bot.handle("tg:1", "/cek", TelegramHTML())[0]


def test_rate_limit_per_chat(bot):
    for _ in range(3):
        bot.handle("tg:1", "TLKM laba naik 20%", TelegramHTML())
    assert "Batas 3" in bot.handle("tg:1", "TLKM laba naik 20%", TelegramHTML())[0]
    assert "Batas" not in bot.handle("tg:2", "TLKM laba naik 20%", TelegramHTML())[0]


def test_whatsapp_markup_neutralises_format_chars():
    m = WhatsAppText()
    assert m.bold("A") == "*A*"
    assert "​*" in m.esc("*naik* 200%")


def test_split_message_respects_limit():
    parts = split_message("\n\n".join(["a" * 30] * 10), 100)
    assert all(len(p) <= 100 for p in parts) and "".join(parts).count("a") == 300


# --- Telegram ----------------------------------------------------------------------

def telegram(bot, fixture_dir, updates):
    sent = []

    def handler(req: httpx.Request):
        method = req.url.path.rsplit("/", 1)[-1]
        body = json.loads(req.content or b"{}")
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": updates})
        sent.append((method, body))
        return httpx.Response(200, json={"ok": True, "result": {}})

    tg = TelegramBot("TOKEN", bot, bot.store, transport=httpx.MockTransport(handler))
    return tg, sent


def test_telegram_private_group_and_dedupe(bot, fixture_dir):
    updates = [
        {"update_id": 1, "message": {"message_id": 10, "chat": {"id": 5, "type": "private"},
                                     "from": {"language_code": "id"}, "text": "TLKM laba naik 20% YoY"}},
        {"update_id": 2, "message": {"message_id": 11, "chat": {"id": -7, "type": "group"},
                                     "text": "gimana kabar semua"}},  # group chatter: ignored
        {"update_id": 3, "message": {"message_id": 12, "chat": {"id": -7, "type": "group"}, "text": "/cek@NeracaBot",
                                     "reply_to_message": {"text": "TLKM dividen yield 12%"}}},
    ]
    tg, sent = telegram(bot, fixture_dir, updates)
    assert tg.poll_once() == 3 and tg.offset == 4
    msgs = [b for m, b in sent if m == "sendMessage"]
    assert [m["chat_id"] for m in msgs] == [5, -7]
    assert msgs[0]["parse_mode"] == "HTML" and msgs[0]["reply_parameters"] == {"message_id": 10}
    assert "Tidak sesuai" in msgs[1]["text"]  # 12% vs 9.26% TTM
    sent.clear()
    tg.poll_once()  # same updates re-delivered: answered once only
    assert not [b for m, b in sent if m == "sendMessage"]


# --- WhatsApp ----------------------------------------------------------------------

def wa_client(bot, fixture_dir, sent, **overrides):
    wa = {"whatsapp_token": "T", "whatsapp_phone_number_id": "PNID",
          "whatsapp_verify_token": "verify-me", "whatsapp_app_secret": "secret", **overrides}
    s = replace(settings(fixture_dir), **wa)
    transport = httpx.MockTransport(lambda req: sent.append((str(req.url), json.loads(req.content))) or
                                    httpx.Response(200, json={"messages": [{"id": "out"}]}))
    adapter = whatsapp.WhatsAppAdapter(s, bot, bot.store, transport=transport)
    api.app.dependency_overrides[whatsapp.get_adapter] = lambda: adapter
    return TestClient(api.app)


def signed(body: dict, secret="secret"):
    raw = json.dumps(body).encode()
    return raw, {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
                 "Content-Type": "application/json"}


def test_whatsapp_verification_handshake(bot, fixture_dir):
    c = wa_client(bot, fixture_dir, [])
    ok = c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                             "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    bad = c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                              "hub.challenge": "1"})
    assert bad.status_code == 403


def test_whatsapp_message_flow_signature_and_dedupe(bot, fixture_dir):
    sent = []
    c = wa_client(bot, fixture_dir, sent)
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "6281234", "id": "wamid.1", "type": "text", "text": {"body": "TLKM laba naik 20% YoY"}}]}}]}]}
    raw, headers = signed(payload)
    assert c.post("/webhooks/whatsapp", content=raw, headers={**headers, "X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    assert c.post("/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
    [(url, body)] = sent
    assert url.endswith("/PNID/messages") and body["to"] == "6281234"
    assert body["context"] == {"message_id": "wamid.1"}
    assert "*TLKM · Pertumbuhan laba*" in body["text"]["body"]
    c.post("/webhooks/whatsapp", content=raw, headers=headers)  # Meta retry: ignored
    assert len(sent) == 1


def test_whatsapp_unconfigured_rejects(bot, fixture_dir):
    c = wa_client(bot, fixture_dir, [], whatsapp_app_secret="")
    raw, headers = signed({"entry": []})
    assert c.post("/webhooks/whatsapp", content=raw, headers=headers).status_code == 503


def test_telegram_photo_is_downloaded_and_checked(bot, fixture_dir, monkeypatch):
    got = {}
    monkeypatch.setattr(bot.checker, "check", lambda text, llm=None, images=None: got.update(text=text, images=images) or
                        __import__("cekfakta.schema", fromlist=["CheckResult"]).CheckResult(
                            message=text, verdicts=[], companies=[], extractor="rules", data_source="fixtures"))
    upd = [{"update_id": 9, "message": {"message_id": 1, "chat": {"id": 5, "type": "private"}, "caption": "benar?",
                                        "photo": [{"file_id": "small", "file_size": 100}, {"file_id": "big", "file_size": 900}]}}]
    calls = []

    def handler(req: httpx.Request):
        path = req.url.path
        calls.append(path)
        if path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": upd})
        if path.endswith("/getFile"):
            assert json.loads(req.content)["file_id"] == "big"
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/1.jpg"}})
        if "/file/bot" in path:
            return httpx.Response(200, content=b"JPEGDATA")
        return httpx.Response(200, json={"ok": True, "result": {}})

    tg = TelegramBot("TOKEN", bot, bot.store, transport=httpx.MockTransport(handler))
    tg.poll_once()
    assert got["text"] == "benar?" and got["images"][0].data == b"JPEGDATA"
    assert any(p.endswith("/file/botTOKEN/photos/1.jpg") for p in calls)


def test_whatsapp_image_is_downloaded(bot, fixture_dir, monkeypatch):
    got = {}
    monkeypatch.setattr(bot.checker, "check", lambda text, llm=None, images=None: got.update(images=images) or
                        __import__("cekfakta.schema", fromlist=["CheckResult"]).CheckResult(
                            message=text, verdicts=[], companies=[], extractor="rules", data_source="fixtures"))
    s = replace(settings(fixture_dir), whatsapp_token="T", whatsapp_phone_number_id="PNID",
                whatsapp_verify_token="v", whatsapp_app_secret="secret")

    def handler(req: httpx.Request):
        if req.url.path.endswith("/MEDIA1"):
            return httpx.Response(200, json={"url": "https://lookaside.example/img", "mime_type": "image/png", "file_size": 10})
        if req.url.host == "lookaside.example":
            assert req.headers["Authorization"] == "Bearer T"
            return httpx.Response(200, content=b"PNGDATA")
        return httpx.Response(200, json={})

    wa = whatsapp.WhatsAppAdapter(s, bot, bot.store, transport=httpx.MockTransport(handler))
    wa.handle_message({"from": "62811", "id": "wamid.9", "type": "image", "image": {"id": "MEDIA1", "caption": "cek"}})
    assert got["images"][0].data == b"PNGDATA" and got["images"][0].mime == "image/png"


def test_score_rounds_half_up_like_the_web_app():
    from cekfakta.bot.core import accuracy_score
    from cekfakta.schema import Claim, ClaimType, Text, Verdict, VerdictLabel as L

    def v(label):
        return Verdict(claim=Claim(ticker="TLKM", claim_type=ClaimType.PROFIT_GROWTH, source_text="x"),
                       label=label, reason=Text(id="", en=""))
    # 2 matches + 1 partial out of 4 checkable = 62.5 -> 63 (web shows 63)
    assert accuracy_score([v(L.SESUAI), v(L.SESUAI), v(L.SEBAGIAN), v(L.TIDAK_SESUAI), v(L.TIDAK_DAPAT)]) == 63
