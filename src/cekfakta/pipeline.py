"""message -> claims -> company facts -> verdicts."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from .config import Settings
from .extract import RuleExtractor
from .facts import CompanyFacts, DataSource, TickerNotFound
from .ingest import Fetcher, Source, SourceInfo, find_urls, read_source, strip_urls
from .llm import PROVIDERS, Image, LLMError, LLMExtractor
from .schema import CheckResult, ClaimType, Text, Verdict
from .sectors_client import BudgetExceeded, SectorsError, normalize_symbol
from .verify import verify

log = logging.getLogger(__name__)

MAX_TICKERS_PER_CHECK = 5  # a pasted essay shouldn't drain the credit budget

_LLM_ERROR_TEXT = {
    "auth": ("Kunci API {label} ditolak. Periksa kuncinya.",
             "{label} rejected the API key. Check the key."),
    "rate_limit": ("Batas pemakaian {label} tercapai.",
                   "{label} rate limit reached."),
    "bad_request": ("{label} menolak permintaan; model '{model}' mungkin tidak tersedia untuk kunci ini.",
                    "{label} rejected the request; model '{model}' may not be available to this key."),
    "unavailable": ("{label} tidak dapat dihubungi.", "{label} could not be reached."),
    "empty": ("{label} tidak mengembalikan hasil.", "{label} returned no result."),
}
_MEDIA_NEEDS_AI = Text(
    id="Membaca tangkapan layar butuh penyedia AI (atur di ⚙ AI). Hanya teks pesan yang dicek.",
    en="Reading screenshots needs an AI provider (set it in ⚙ AI). Only the message text was checked.",
)
_RULES_FALLBACK = Text(id="Memakai ekstraktor berbasis aturan.", en="Using the rule-based extractor instead.")


def llm_error_text(e: LLMError, extractor: LLMExtractor) -> Text:
    id_, en = _LLM_ERROR_TEXT[e.kind]
    params = {"label": PROVIDERS[extractor.name].label, "model": extractor.model}
    return Text(id=id_.format(**params), en=en.format(**params))


class LLMConfigError(ValueError):
    """The requested provider can't be used (no key, user keys disabled). Maps to HTTP 400."""


@dataclass(frozen=True)
class LLMChoice:
    """What the caller asked for. Empty fields fall back to the server's configuration."""
    provider: str = ""
    api_key: str = ""
    model: str = ""

    def __repr__(self) -> str:  # never print the key
        return f"LLMChoice(provider={self.provider!r}, model={self.model!r}, key={'set' if self.api_key else 'none'})"


class Checker:
    def __init__(self, settings: Settings, source: DataSource):
        self.settings = settings
        self.source = source
        self.fallback = RuleExtractor()
        self.fetcher = Fetcher()
        # Serializes Sectors fetches so the budget check and ledger stay consistent.
        self._fetch_lock = threading.Lock()

    def extractor_for(self, choice: LLMChoice | None) -> LLMExtractor | RuleExtractor:
        """Resolve a request's LLM choice against server config. Raises LLMConfigError."""
        choice = choice or LLMChoice()
        provider = choice.provider or self.settings.default_llm_provider
        if provider == "rules":
            return self.fallback
        if provider not in PROVIDERS:
            raise LLMConfigError(f"Penyedia AI tidak dikenal: {provider!r}.")
        if choice.api_key and not self.settings.allow_user_keys:
            raise LLMConfigError("Server ini tidak menerima kunci API dari pengguna.")
        key = choice.api_key or self.settings.llm_keys.get(provider, "")
        if not key:
            raise LLMConfigError(f"Belum ada kunci API untuk {PROVIDERS[provider].label}.")
        model = choice.model or self.settings.llm_models.get(provider) or None
        return LLMExtractor(provider, key, model)

    def _extract(self, message: str, extractor, notes: list[str]):
        if isinstance(extractor, RuleExtractor):
            return extractor.extract(message), "rules", None
        try:
            return extractor.extract(message), extractor.name, extractor.model
        except LLMError as e:  # degrade to rules rather than fail the whole check
            log.warning("%s extraction failed (%s), using rules", extractor.name, e.kind)
            err = llm_error_text(e, extractor)
            notes.append(Text(id=f"{err.id} {_RULES_FALLBACK.id}", en=f"{err.en} {_RULES_FALLBACK.en}"))
            return self.fallback.extract(message), "rules", None

    def _facts(self, ticker: str, notes: list[Text]) -> CompanyFacts | None:
        try:
            with self._fetch_lock:
                report = self.source.report(ticker)
                quarters = self.source.quarterly(ticker)
                daily = self._daily(ticker)
            return CompanyFacts(ticker=ticker, report=report, quarters=quarters, daily=daily)
        except TickerNotFound:
            if self.source.name == "fixtures":
                notes.append(Text(id=f"{ticker} tidak ada di data offline. Set SECTORS_API_KEY untuk data live.",
                                  en=f"{ticker} isn't in the offline data. Set SECTORS_API_KEY for live data."))
            else:
                notes.append(Text(id=f"{ticker} tidak ditemukan di IDX.", en=f"{ticker} was not found on IDX."))
        except BudgetExceeded:
            notes.append(Text(id=f"Batas kredit API tercapai; {ticker} tidak dicek.",
                              en=f"API credit cap reached; {ticker} was not checked."))
        except SectorsError as e:
            notes.append(Text(id=f"Gagal mengambil data {ticker} (HTTP {e.status}).",
                              en=f"Couldn't fetch data for {ticker} (HTTP {e.status})."))
        return None

    def _daily(self, ticker: str) -> list | None:
        """Price history is for the chart only; a failure here never blocks the check."""
        try:
            return self.source.daily(ticker)
        except (TickerNotFound, BudgetExceeded, SectorsError) as e:
            log.info("No daily prices for %s: %s", ticker, e)
            return None

    def _extract_media(self, text: str, images: list[Image], video_url: str | None, extractor,
                       notes: list[Text]):
        """Screenshots / video need an LLM that can see them; otherwise fall back to the text."""
        if isinstance(extractor, RuleExtractor):
            if images:
                notes.append(_MEDIA_NEEDS_AI)
            return extractor.extract(text), "rules", None, None
        try:
            claims, media_text = extractor.extract_media(text, images, video_url)
            return claims, extractor.name, extractor.model, media_text or None
        except LLMError as e:
            log.warning("%s media extraction failed (%s), using rules", extractor.name, e.kind)
            err = llm_error_text(e, extractor)
            notes.append(Text(id=f"{err.id} {_RULES_FALLBACK.id}", en=f"{err.en} {_RULES_FALLBACK.en}"))
            return self.fallback.extract(text), "rules", None, None

    def check(self, message: str, llm: LLMChoice | None = None, images: list[Image] | None = None) -> CheckResult:
        notes: list[Text] = []
        images = images or []
        extractor = self.extractor_for(llm)
        spent_before = self.source.credits_spent()

        # Links: read what's behind them and check that content together with the message.
        urls = find_urls(message)
        sources: list[Source] = [read_source(u, self.fetcher) for u in urls]
        text = strip_urls(message) if urls else message
        for s in sources:
            if s.text:
                text += f"\n\n[{s.platform}: {s.title or s.url}]\n{s.text}"
        # Gemini can watch a public YouTube video; other providers use its title/description.
        video = next((s for s in sources if s.video_url and s.status != "error"), None)
        video_url = video.video_url if video and getattr(extractor, "name", "") == "gemini" else None

        media_text = None
        if images or video_url:
            claims, extractor_name, model, media_text = self._extract_media(text, images, video_url, extractor, notes)
        else:
            claims, extractor_name, model = self._extract(text, extractor, notes)

        facts: dict[str, CompanyFacts | None] = {}
        verdicts: list[Verdict] = []
        for claim in claims:
            try:
                claim.ticker = normalize_symbol(claim.ticker)
            except ValueError:
                claim.claim_type = ClaimType.UNVERIFIABLE
                claim.unverifiable_reason = claim.unverifiable_reason or \
                    f"'{claim.ticker}' bukan kode saham IDX yang valid."
                claim.unverifiable_reason_en = claim.unverifiable_reason_en or \
                    f"'{claim.ticker}' is not a valid IDX stock code."
            if claim.claim_type != ClaimType.UNVERIFIABLE and claim.ticker not in facts:
                if len(facts) >= MAX_TICKERS_PER_CHECK:
                    notes.append(Text(
                        id=f"Maksimal {MAX_TICKERS_PER_CHECK} saham per pengecekan; {claim.ticker} dilewati.",
                        en=f"At most {MAX_TICKERS_PER_CHECK} stocks per check; {claim.ticker} was skipped."))
                    facts[claim.ticker] = None
                else:
                    facts[claim.ticker] = self._facts(claim.ticker, notes)
            verdicts.append(verify(claim, facts.get(claim.ticker)))

        if not claims:
            notes.append(Text(
                id="Tidak ada klaim yang bisa dicek. Coba sertakan kode saham dan angka "
                   "(mis. 'laba TLKM naik 20% YoY').",
                en="No checkable claims found. Try including a stock code and a number "
                   "(e.g. 'laba TLKM naik 20% YoY')."))

        return CheckResult(
            message=message,
            verdicts=verdicts,
            companies=[f.snapshot() for f in facts.values() if f is not None],
            extractor=extractor_name,
            model=model,
            data_source=self.source.name,
            credits_spent=self.source.credits_spent() - spent_before,
            notes=notes,
            sources=[SourceInfo.of(s, analyzed_video=bool(video_url) and s is video) for s in sources],
            media_text=media_text,
        )
