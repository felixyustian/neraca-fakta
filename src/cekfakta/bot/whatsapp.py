"""WhatsApp Cloud API webhook (Meta). Served by the API server at /webhooks/whatsapp.

Setup (Meta for Developers):
1. Create an app, add the WhatsApp product, note the phone number ID and an access token
   (WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TOKEN) and the app secret (WHATSAPP_APP_SECRET).
2. Deploy the API server on a public HTTPS URL (or tunnel a local one, e.g. ngrok).
3. Webhook: callback URL https://<host>/webhooks/whatsapp, verify token = WHATSAPP_VERIFY_TOKEN,
   subscribe to the "messages" field.

Users message the bot's number; replies are free-form text inside WhatsApp's 24-hour
customer-service window, which a user's own message always opens.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from functools import lru_cache
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..config import Settings, load_settings
from ..facts import make_source
from ..llm import Image
from ..market import MarketService
from ..pipeline import Checker
from ..store import Store
from .core import ChatBot
from .markup import WhatsAppText

log = logging.getLogger(__name__)


class WhatsAppAdapter:
    def __init__(self, settings: Settings, bot: ChatBot, store: Store,
                 transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.bot = bot
        self.store = store
        self.markup = WhatsAppText()
        self.http = httpx.Client(
            base_url=f"https://graph.facebook.com/{settings.whatsapp_api_version}/",
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            timeout=20.0, transport=transport,
        )

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.whatsapp_token and s.whatsapp_phone_number_id and s.whatsapp_verify_token
                    and s.whatsapp_app_secret)

    def signature_ok(self, body: bytes, header: str | None) -> bool:
        if not header or not header.startswith("sha256="):
            return False
        expected = hmac.new(self.settings.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header.removeprefix("sha256="))

    @staticmethod
    def messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Incoming user messages from a webhook payload (status updates are ignored)."""
        out = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                out.extend(change.get("value", {}).get("messages", []))
        return out

    def send(self, to: str, text: str, reply_to: str | None = None) -> None:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp", "to": to, "type": "text",
            "text": {"body": text, "preview_url": False},
        }
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        resp = self.http.post(f"{self.settings.whatsapp_phone_number_id}/messages", json=payload)
        if resp.status_code >= 400:
            log.warning("WhatsApp send failed (%s): %s", resp.status_code, resp.text[:300])

    def download_image(self, media: dict[str, Any]) -> list[Image]:
        """Media is fetched in two steps: its URL from the Graph API, then the bytes (same token)."""
        meta = self.http.get(media["id"])
        meta.raise_for_status()
        info = meta.json()
        if info.get("file_size", 0) > 5 * 1024 * 1024:
            return []
        data = self.http.get(info["url"])
        data.raise_for_status()
        return [Image(data=data.content, mime=info.get("mime_type") or media.get("mime_type") or "image/jpeg")]

    def handle_message(self, msg: dict[str, Any]) -> None:
        if not self.store.first_time_seen(f"wa:{msg.get('id')}"):
            return  # Meta retries deliveries; answer each message once
        kind = msg.get("type")
        text = (msg.get("text") or {}).get("body") if kind == "text" else (msg.get(kind) or {}).get("caption")
        images = self.download_image(msg["image"]) if kind == "image" and msg.get("image") else []
        sender = msg["from"]
        replies = self.bot.handle(f"wa:{sender}", text or "", self.markup, images=images)
        for i, reply in enumerate(replies):
            self.send(sender, reply, reply_to=msg.get("id") if i == 0 else None)


@lru_cache
def get_adapter() -> WhatsAppAdapter:
    settings = load_settings()
    store = Store(settings.cache_path)
    checker = Checker(settings, make_source(settings))
    market = MarketService(settings) if settings.market_panels else None
    bot = ChatBot(checker, store, market, settings.bot_checks_per_hour, settings.public_app_url)
    return WhatsAppAdapter(settings, bot, store)


router = APIRouter()


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
           challenge: str = Query("", alias="hub.challenge"),
           wa: WhatsAppAdapter = Depends(get_adapter)) -> str:
    """Meta's one-time subscription handshake."""
    expected = wa.settings.whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
        return challenge
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
async def receive(request: Request, background: BackgroundTasks,
                  wa: WhatsAppAdapter = Depends(get_adapter)) -> dict:
    if not wa.configured:
        raise HTTPException(503, "WhatsApp is not configured on this server")
    body = await request.body()
    if not wa.signature_ok(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "Invalid signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    # Acknowledge right away (Meta retries slow webhooks); check and reply in the background.
    for msg in wa.messages(payload):
        background.add_task(wa.handle_message, msg)
    return {"ok": True}
