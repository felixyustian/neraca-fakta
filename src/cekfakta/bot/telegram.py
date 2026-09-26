"""Telegram bot via long polling: runs anywhere (a laptop is fine), no public URL needed.

Setup: talk to @BotFather, /newbot, copy the token into TELEGRAM_BOT_TOKEN in .env.
Run:   python -m cekfakta.bot.telegram   (or `make telegram`)

Private chats: every text (or forwarded message, or photo caption) is fact-checked.
Groups: only /cek <message>, or /cek as a reply to a message, so the bot stays quiet otherwise.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..config import Settings, load_settings
from ..facts import make_source
from ..llm import Image
from ..market import MarketService
from ..pipeline import Checker
from ..store import Store
from .core import ChatBot
from .markup import TelegramHTML

log = logging.getLogger(__name__)

POLL_TIMEOUT_S = 30
MAX_PHOTO_BYTES = 5 * 1024 * 1024
GROUP_COMMANDS = ("/cek", "/check", "/pasar", "/market", "/start", "/help", "/bantuan", "/lang", "/bahasa")


class TelegramBot:
    def __init__(self, token: str, bot: ChatBot, store: Store, transport: httpx.BaseTransport | None = None):
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather first.")
        self._token = token
        self.bot = bot
        self.store = store
        self.markup = TelegramHTML()
        self.offset: int | None = None
        # Long-poll requests stay open for POLL_TIMEOUT_S; the client timeout must exceed it.
        self.http = httpx.Client(base_url=f"https://api.telegram.org/bot{token}/",
                                 timeout=POLL_TIMEOUT_S + 15, transport=transport)

    def _call(self, method: str, **payload: Any) -> Any:
        resp = self.http.post(method, json=payload)
        body = resp.json()
        if not body.get("ok"):
            # The URL contains the token; log only the method and Telegram's description.
            raise RuntimeError(f"Telegram {method} failed: {body.get('description')}")
        return body["result"]

    def _text_for(self, msg: dict[str, Any]) -> str | None:
        """What to check for this message, or None to stay silent."""
        text = msg.get("text") or msg.get("caption") or ""
        if msg.get("chat", {}).get("type") == "private":
            return text
        first = text.split()[0].lower().split("@")[0] if text.split() else ""
        if first not in GROUP_COMMANDS:
            return None
        if first in ("/cek", "/check") and len(text.split()) == 1:
            replied = msg.get("reply_to_message") or {}
            quoted = replied.get("text") or replied.get("caption")
            if quoted:
                return f"/cek {quoted}"
        return text

    def _photo(self, msg: dict[str, Any]) -> list[Image]:
        """The largest version of an attached photo (or of the photo being replied to with /cek)."""
        photo_msg = msg if msg.get("photo") else (msg.get("reply_to_message") or {})
        sizes = [p for p in photo_msg.get("photo") or [] if p.get("file_size", 0) <= MAX_PHOTO_BYTES]
        if not sizes:
            return []
        file = self._call("getFile", file_id=sizes[-1]["file_id"])
        resp = self.http.get(f"https://api.telegram.org/file/bot{self._token}/{file['file_path']}")
        resp.raise_for_status()
        return [Image(data=resp.content, mime="image/jpeg")]  # Telegram re-encodes photos as JPEG

    def process_update(self, update: dict[str, Any]) -> None:
        msg = update.get("message")
        if not msg or not self.store.first_time_seen(f"tg:{update['update_id']}"):
            return
        text = self._text_for(msg)
        if text is None:
            return
        chat_id = msg["chat"]["id"]
        self._call("sendChatAction", chat_id=chat_id, action="typing")
        images = self._photo(msg)
        replies = self.bot.handle(f"tg:{chat_id}", text, self.markup,
                                  lang_hint=(msg.get("from") or {}).get("language_code"), images=images)
        for i, reply in enumerate(replies):
            self._call("sendMessage", chat_id=chat_id, text=reply, parse_mode="HTML",
                       link_preview_options={"is_disabled": True},
                       **({"reply_parameters": {"message_id": msg["message_id"]}} if i == 0 else {}))

    def poll_once(self) -> int:
        payload: dict[str, Any] = {"timeout": POLL_TIMEOUT_S, "allowed_updates": ["message"]}
        if self.offset is not None:
            payload["offset"] = self.offset
        updates = self._call("getUpdates", **payload)
        for u in updates:
            self.offset = u["update_id"] + 1
            try:
                self.process_update(u)
            except Exception:  # one bad update must not stop the bot
                log.exception("Failed to handle Telegram update %s", u.get("update_id"))
        return len(updates)

    def run_forever(self) -> None:
        me = self._call("getMe")
        self._call("deleteWebhook")  # polling and a webhook can't both be active
        log.info("Telegram bot @%s is running. Ctrl+C to stop.", me.get("username"))
        backoff = 1
        while True:
            try:
                self.poll_once()
                backoff = 1
            except (httpx.HTTPError, RuntimeError) as e:
                log.warning("Telegram polling error: %s; retrying in %ss", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)


def build(settings: Settings) -> TelegramBot:
    store = Store(settings.cache_path)
    checker = Checker(settings, make_source(settings))
    market = MarketService(settings) if settings.market_panels else None
    bot = ChatBot(checker, store, market, settings.bot_checks_per_hour, settings.public_app_url)
    return TelegramBot(settings.telegram_bot_token, bot, store)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its request lines include the token URL
    try:
        build(load_settings()).run_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
