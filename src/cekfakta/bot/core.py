"""Channel-independent chat logic: commands, language, rate limits, and reply formatting.

Adapters (telegram.py, whatsapp.py) turn platform updates into `handle()` calls and send
back the returned messages. The check itself is the same pipeline the web app uses.
"""
from __future__ import annotations

import logging
import time

from ..llm import Image
from ..market import MarketService
from ..pipeline import Checker
from ..schema import CheckResult, ClaimType, Verdict, VerdictLabel
from ..store import Store
from ..verify import fmt_num, fmt_pct
from .markup import Markup, split_message

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000
QUOTE_CHARS = 160

ICON = {
    VerdictLabel.SESUAI: "✅",
    VerdictLabel.SEBAGIAN: "🟡",
    VerdictLabel.TIDAK_SESUAI: "❌",
    VerdictLabel.TIDAK_DAPAT: "❔",
}
VERDICT = {
    VerdictLabel.SESUAI: {"id": "Sesuai data", "en": "Matches data"},
    VerdictLabel.SEBAGIAN: {"id": "Sebagian sesuai", "en": "Partly matches"},
    VerdictLabel.TIDAK_SESUAI: {"id": "Tidak sesuai", "en": "Doesn't match"},
    VerdictLabel.TIDAK_DAPAT: {"id": "Tidak dapat diverifikasi", "en": "Can't be verified"},
}
CLAIM_TYPE = {
    ClaimType.REVENUE_GROWTH: {"id": "Pertumbuhan pendapatan", "en": "Revenue growth"},
    ClaimType.PROFIT_GROWTH: {"id": "Pertumbuhan laba", "en": "Profit growth"},
    ClaimType.NET_INCOME: {"id": "Laba bersih", "en": "Net income"},
    ClaimType.DIVIDEND_YIELD: {"id": "Dividend yield", "en": "Dividend yield"},
    ClaimType.MARKET_CAP: {"id": "Kapitalisasi pasar", "en": "Market cap"},
    ClaimType.UNVERIFIABLE: {"id": "Tidak dapat dicek", "en": "Not checkable"},
}
TEXT = {
    "name": {"id": "Neraca Fakta", "en": "Fact Ledger"},
    "help": {
        "id": ("Kirim atau teruskan pesan saham ke sini, dan setiap klaim angka akan dicek ke laporan "
               "keuangan resmi emiten IDX. Bisa juga kirim tautan (artikel, blog, YouTube, TikTok, Threads, "
               "Instagram, Facebook, X) atau tangkapan layar.\n\nContoh: \"$TLKM laba naik 20% YoY, dividen yield 9%\"\n\n"
               "Perintah:\n/pasar — ringkasan pasar hari ini\n/bahasa en — reply in English\n/bantuan — pesan ini"),
        "en": ("Send or forward a stock tip here and every numeric claim is checked against official IDX "
               "financial reports. You can also send links (articles, blogs, YouTube, TikTok, Threads, "
               "Instagram, Facebook, X) or screenshots.\n\nExample: \"$TLKM laba naik 20% YoY, dividen yield 9%\"\n\n"
               "Commands:\n/market — today's market summary\n/lang id — balas dalam Bahasa Indonesia\n/help — this message"),
    },
    "group_hint": {
        "id": "Di grup, balas pesan dengan /cek atau tulis /cek <pesan>.",
        "en": "In groups, reply to a message with /cek or write /cek <message>.",
    },
    "lang_set": {"id": "Bahasa diatur ke Bahasa Indonesia.", "en": "Language set to English."},
    "lang_usage": {"id": "Pakai /bahasa id atau /bahasa en.", "en": "Use /lang en or /lang id."},
    "rate_limited": {
        "id": "Batas {n} pengecekan per jam tercapai. Coba lagi nanti.",
        "en": "You've reached {n} checks per hour. Please try again later.",
    },
    "too_long": {"id": "Pesan terlalu panjang (maks. {n} karakter).", "en": "Message too long (max {n} characters)."},
    "error": {"id": "Maaf, terjadi kesalahan saat memeriksa. Coba lagi sebentar lagi.",
              "en": "Sorry, something went wrong while checking. Please try again shortly."},
    "no_claims": {
        "id": "Tidak ada klaim angka yang bisa dicek. Sertakan kode saham dan angka, mis. \"laba TLKM naik 20% YoY\".",
        "en": "No checkable numeric claims found. Include a stock code and a number, e.g. \"laba TLKM naik 20% YoY\".",
    },
    "checked": {"id": "{n} klaim diperiksa", "en": "{n} claims checked"},
    "score": {"id": "Skor kesesuaian {s}/100", "en": "Accuracy score {s}/100"},
    "disclaimer": {"id": "Bukan saran investasi.", "en": "Not investment advice."},
    "open_app": {"id": "Lihat grafik lengkap", "en": "See full charts"},
    "market_off": {"id": "Ringkasan pasar tidak tersedia.", "en": "Market summary isn't available."},
    "market_title": {"id": "Pasar", "en": "Markets"},
    "as_of": {"id": "per {d}", "en": "as of {d}"},
    "gainers": {"id": "Naik", "en": "Gainers"},
    "losers": {"id": "Turun", "en": "Losers"},
    "fx": {"id": "Kurs Rupiah", "en": "Rupiah rates"},
    "news": {"id": "Berita terbaru", "en": "Latest news"},
    "sources": {"id": "Sumber yang dibaca", "en": "Sources read"},
    "video_analyzed": {"id": "video dianalisis", "en": "video analysed"},
}
PLATFORM = {"web": "Web", "youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram",
            "threads": "Threads", "facebook": "Facebook", "x": "X"}
SOURCE_ICON = {"ok": "📄", "partial": "📄", "blocked": "🔒", "error": "⚠️"}

HELP_WORDS = {"/start", "/help", "/bantuan", "/mulai", "start", "help", "bantuan", "menu", "halo", "hi", "hello"}
MARKET_WORDS = {"/pasar", "/market", "pasar", "market"}
LANG_WORDS = {"/lang", "/bahasa", "lang", "bahasa"}


def tr(key: str, lang: str, **kw) -> str:
    return TEXT[key][lang].format(**kw)


def accuracy_score(verdicts: list[Verdict]) -> int | None:
    """Same rule as the web app: match 1, partial 0.5, over checkable claims."""
    checkable = [v for v in verdicts if v.label != VerdictLabel.TIDAK_DAPAT]
    if not checkable:
        return None
    pts = sum(1 if v.label == VerdictLabel.SESUAI else 0.5 if v.label == VerdictLabel.SEBAGIAN else 0
              for v in checkable)
    # Round half up, like the web app's Math.round (Python's round() would give 62 for 62.5).
    return int(pts / len(checkable) * 100 + 0.5)


def _delta(x: float | None, lang: str) -> str:
    if x is None:
        return ""
    arrow = "▲" if x >= 0.005 else "▼" if x <= -0.005 else "•"  # rounds to 0,00%: flat
    return f"{arrow}{fmt_num(abs(x), 2, lang)}%"


class ChatBot:
    def __init__(self, checker: Checker, store: Store, market: MarketService | None = None,
                 checks_per_hour: int = 20, app_url: str = ""):
        self.checker = checker
        self.store = store
        self.market = market
        self.checks_per_hour = checks_per_hour
        self.app_url = app_url

    def lang_for(self, chat_key: str, hint: str | None = None) -> str:
        saved = self.store.bot_lang(chat_key)
        if saved:
            return saved
        return "en" if (hint or "").lower().startswith("en") else "id"

    def handle(self, chat_key: str, text: str, m: Markup, lang_hint: str | None = None,
               images: list[Image] | None = None) -> list[str]:
        """Reply messages for one incoming text (and optional photos). chat_key is channel-prefixed, e.g. 'tg:123'."""
        lang = self.lang_for(chat_key, lang_hint)
        text = (text or "").strip()
        words = text.split()
        first = words[0].lower().split("@")[0] if words else ""

        if images:
            if first in ("/cek", "/check"):
                text = text[len(words[0]):].strip()
            return self.check(chat_key, text, lang, m, images)
        if not text or (len(words) == 1 and first in HELP_WORDS):
            return [f"{m.bold(tr('name', lang))}\n\n{m.esc(tr('help', lang))}"]
        if first in LANG_WORDS and len(words) <= 2:
            if len(words) == 2 and words[1].lower() in ("id", "en"):
                lang = words[1].lower()
                self.store.set_bot_lang(chat_key, lang)
                return [m.esc(tr("lang_set", lang))]
            return [m.esc(tr("lang_usage", lang))]
        if len(words) == 1 and first in MARKET_WORDS:
            return self._market(lang, m)
        if first.startswith("/") and first not in ("/cek", "/check"):
            return [f"{m.bold(tr('name', lang))}\n\n{m.esc(tr('help', lang))}"]
        if first in ("/cek", "/check"):
            text = text[len(words[0]):].strip()
            if not text:
                return [m.esc(tr("group_hint", lang))]
        return self.check(chat_key, text, lang, m)

    def check(self, chat_key: str, text: str, lang: str, m: Markup, images: list[Image] | None = None) -> list[str]:
        if len(text) > MAX_INPUT_CHARS:
            return [m.esc(tr("too_long", lang, n=MAX_INPUT_CHARS))]
        if self.store.bot_checks_since(chat_key, time.time() - 3600) >= self.checks_per_hour:
            return [m.esc(tr("rate_limited", lang, n=self.checks_per_hour))]
        self.store.record_bot_check(chat_key)
        try:
            result = self.checker.check(text, None, images)
        except Exception:  # never leak internals into a chat
            log.exception("Bot check failed for %s", chat_key)
            return [m.esc(tr("error", lang))]
        return split_message(self.format_result(result, lang, m), m.max_len)

    # --- formatting -------------------------------------------------------------
    def _sources_block(self, r: CheckResult, lang: str, m: Markup) -> str | None:
        if not r.sources:
            return None
        lines = [m.bold(tr("sources", lang))]
        for s in r.sources:
            label = f"{PLATFORM[s.platform]}: {s.title or s.url}"[:120]
            if s.analyzed_video:
                label += f" ({tr('video_analyzed', lang)})"
            line = f"{SOURCE_ICON[s.status]} {m.esc(label)}"
            if s.note and s.status != "ok":
                line += f"\n   {m.italic(getattr(s.note, lang))}"
            lines.append(line)
        return "\n".join(lines)

    def format_result(self, r: CheckResult, lang: str, m: Markup) -> str:
        sources = self._sources_block(r, lang, m)
        if not r.verdicts:
            return "\n\n".join(x for x in [sources, m.esc(tr("no_claims", lang))] if x)
        blocks = []
        score = accuracy_score(r.verdicts)
        head = f"🔎 {m.bold(tr('name', lang))} · {m.esc(tr('checked', lang, n=len(r.verdicts)))}"
        if score is not None:
            head += f"\n{m.esc(tr('score', lang, s=score))}"
        blocks.append(head)
        if sources:
            blocks.append(sources)

        for v in r.verdicts:
            c = v.claim
            quote = c.source_text if len(c.source_text) <= QUOTE_CHARS else c.source_text[:QUOTE_CHARS - 1] + "…"
            lines = [
                f"{ICON[v.label]} {m.bold(f'{c.ticker} · {CLAIM_TYPE[c.claim_type][lang]}')} — {m.esc(VERDICT[v.label][lang])}",
                m.italic(f"“{quote}”"),
            ]
            # The reason already states claim vs data with the period; no separate numbers line.
            lines.append(m.esc(getattr(v.reason, lang)))
            blocks.append("\n".join(lines))

        for note in r.notes:
            blocks.append(f"ℹ️ {m.esc(getattr(note, lang))}")
        foot = m.italic(tr("disclaimer", lang))
        if self.app_url:
            foot += "\n" + m.link(tr("open_app", lang), self.app_url)
        blocks.append(foot)
        return "\n\n".join(blocks)

    def _market(self, lang: str, m: Markup) -> list[str]:
        if not self.market:
            return [m.esc(tr("market_off", lang))]
        s = self.market.snapshot()
        blocks = []
        if s.ihsg:
            head = f"📊 {m.bold(tr('market_title', lang))} · {m.esc(tr('as_of', lang, d=s.ihsg.date))}"
            rows = [f"IHSG {fmt_num(s.ihsg.value, 2, lang)} {_delta(s.ihsg.change_pct, lang)}"]
            rows += [f"{q.code} {fmt_num(q.value, 2, lang)} {_delta(q.change_pct, lang)}" for q in s.indices[:4]]
            blocks.append(head + "\n" + m.esc("\n".join(rows)))
        if s.gainers or s.losers:
            fmt = lambda xs: ", ".join(f"{x.symbol} {fmt_pct(x.change_pct, lang)}" for x in xs[:5])
            blocks.append(f"{m.bold(tr('gainers', lang))}: {m.esc(fmt(s.gainers))}\n"
                          f"{m.bold(tr('losers', lang))}: {m.esc(fmt(s.losers))}")
        if s.forex:
            fx = " · ".join(f"{f.currency} {fmt_num(f.rate, 2 if f.rate < 1000 else 0, lang)}" for f in s.forex[:4])
            blocks.append(f"{m.bold(tr('fx', lang))}\n{m.esc(fx)}")
        if s.news:
            items = [f"• {m.link(n.title, n.url)} ({m.esc(n.source)})" for n in s.news[:3]]
            blocks.append(f"{m.bold(tr('news', lang))}\n" + "\n".join(items))
        if not blocks:
            return [m.esc(tr("market_off", lang))]
        blocks.append(m.italic(tr("disclaimer", lang)))
        return split_message("\n\n".join(blocks), m.max_len)
