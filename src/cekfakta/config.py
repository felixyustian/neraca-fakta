"""Runtime configuration. Secrets come from the environment / .env, never from code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    sectors_api_key: str
    sectors_base_url: str
    cache_path: Path
    # Stop making paid calls once the local ledger reaches this many credits.
    credit_hard_cap: int
    # Credits already spent before this ledger existed (e.g. manual tests in the portal).
    credit_offset: int
    # "live" calls Sectors; "fixtures" reads fixtures/raw/ (no key, no credits); "auto" picks.
    data_source: str = "auto"
    # LLM claim extraction. Keys per provider; blank means the provider has no server key.
    # llm_provider: "anthropic" | "openai" | "gemini" | "rules" | "" (first provider with a key).
    llm_provider: str = ""
    llm_keys: dict[str, str] = field(default_factory=dict)
    llm_models: dict[str, str] = field(default_factory=dict)  # overrides of default models
    # Let web users supply their own key per request (never stored server-side).
    allow_user_keys: bool = True
    # Market side panels (indices, movers, news, forex). They keep this many credits in
    # reserve under the cap so they never starve fact-checks.
    market_panels: bool = True
    market_credit_reserve: int = 100
    # Chat bots. Each chat may run this many fact-checks per hour (they spend credits).
    bot_checks_per_hour: int = 20
    public_app_url: str = ""
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_display_number: str = ""  # public number for wa.me links, digits only
    fixtures_dir: Path = ROOT / "fixtures" / "raw"

    @property
    def resolved_data_source(self) -> str:
        if self.data_source in ("live", "fixtures"):
            return self.data_source
        return "live" if self.sectors_api_key else "fixtures"

    @property
    def default_llm_provider(self) -> str:
        """Provider used when the request doesn't pick one; "rules" if no key is configured."""
        if self.llm_provider == "rules" or self.llm_keys.get(self.llm_provider):
            return self.llm_provider
        for p in ("anthropic", "openai", "gemini"):
            if self.llm_keys.get(p):
                return p
        return "rules"


def load_settings() -> Settings:
    key = os.getenv("SECTORS_API_KEY", "").strip()
    return Settings(
        sectors_api_key=key,
        sectors_base_url=os.getenv("SECTORS_BASE_URL", "https://api.sectors.app").rstrip("/"),
        cache_path=Path(os.getenv("CACHE_PATH", ROOT / "data" / "cache.sqlite")),
        credit_hard_cap=int(os.getenv("CREDIT_HARD_CAP", "950")),
        credit_offset=int(os.getenv("CREDIT_OFFSET", "0")),
        data_source=os.getenv("DATA_SOURCE", "auto").strip().lower(),
        llm_provider=os.getenv("LLM_PROVIDER", "").strip().lower(),
        llm_keys={p: os.getenv(f"{p.upper()}_API_KEY", "").strip()
                  for p in ("anthropic", "openai", "gemini")},
        llm_models={p: m for p in ("anthropic", "openai", "gemini")
                    if (m := os.getenv(f"{p.upper()}_MODEL", "").strip())},
        allow_user_keys=os.getenv("ALLOW_USER_KEYS", "true").strip().lower() in ("1", "true", "yes"),
        market_panels=os.getenv("MARKET_PANELS", "true").strip().lower() in ("1", "true", "yes"),
        market_credit_reserve=int(os.getenv("MARKET_CREDIT_RESERVE", "100")),
        bot_checks_per_hour=int(os.getenv("BOT_CHECKS_PER_HOUR", "20")),
        public_app_url=os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@"),
        whatsapp_token=os.getenv("WHATSAPP_TOKEN", "").strip(),
        whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
        whatsapp_verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip(),
        whatsapp_app_secret=os.getenv("WHATSAPP_APP_SECRET", "").strip(),
        whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v21.0").strip(),
        whatsapp_display_number="".join(ch for ch in os.getenv("WHATSAPP_DISPLAY_NUMBER", "") if ch.isdigit()),
    )
