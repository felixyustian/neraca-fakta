"""Per-channel text styling. Telegram takes HTML; WhatsApp has its own *bold* / _italic_ syntax."""
from __future__ import annotations

import html
import re


class TelegramHTML:
    name = "telegram"
    max_len = 4096

    def esc(self, s: str) -> str:
        return html.escape(s, quote=False)

    def bold(self, s: str) -> str:
        return f"<b>{self.esc(s)}</b>"

    def italic(self, s: str) -> str:
        return f"<i>{self.esc(s)}</i>"

    def link(self, text: str, url: str) -> str:
        return f'<a href="{html.escape(url, quote=True)}">{self.esc(text)}</a>'


class WhatsAppText:
    name = "whatsapp"
    max_len = 4096
    _FORMAT_CHARS = re.compile(r"([*_~`])")

    def esc(self, s: str) -> str:
        # WhatsApp has no escape syntax; a zero-width space breaks accidental formatting
        # from characters in quoted user text.
        return self._FORMAT_CHARS.sub("​\\1", s)

    def bold(self, s: str) -> str:
        return f"*{self.esc(s)}*"

    def italic(self, s: str) -> str:
        return f"_{self.esc(s)}_"

    def link(self, text: str, url: str) -> str:
        return f"{self.esc(text)}: {url}"


Markup = TelegramHTML | WhatsAppText


def split_message(text: str, limit: int) -> list[str]:
    """Split at paragraph breaks so each part fits the channel's message limit."""
    parts, cur = [], ""
    for para in text.split("\n\n"):
        candidate = f"{cur}\n\n{para}" if cur else para
        if len(candidate) <= limit:
            cur = candidate
            continue
        if cur:
            parts.append(cur)
        while len(para) > limit:  # a single oversized paragraph: hard cut
            parts.append(para[:limit])
            para = para[limit:]
        cur = para
    if cur:
        parts.append(cur)
    return parts
