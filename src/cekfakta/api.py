"""HTTP API, and the built frontend (web/dist) when it exists.

Run:  uvicorn cekfakta.api:app --app-dir src --reload

LLM choice per request (all optional; the server's .env config fills the gaps):
  X-LLM-Provider: anthropic | openai | gemini | rules
  X-LLM-Key:      the user's own key, used for this request only, never stored or logged
  X-LLM-Model:    model override
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import __version__
from .config import ROOT, load_settings
from .facts import FixtureSource, make_source
from .bot import whatsapp
from .llm import PROVIDERS, Image, LLMError
from .market import WATCHLIST_MAX, MarketService, MarketSnapshot, WatchQuote
from .pipeline import Checker, LLMChoice, LLMConfigError, llm_error_text
from .schema import CheckResult

MAX_MESSAGE_CHARS = 4000
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
# Short message with one clear claim, used by /api/llm/test to prove a key works.
TEST_MESSAGE = "Laba TLKM naik 20% YoY."


class CheckRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


@lru_cache
def get_checker() -> Checker:
    settings = load_settings()
    return Checker(settings, make_source(settings))


@lru_cache
def get_market() -> MarketService | None:
    settings = load_settings()
    return MarketService(settings) if settings.market_panels else None


def llm_choice(
    x_llm_provider: str = Header("", max_length=20),
    x_llm_key: str = Header("", max_length=512),
    x_llm_model: str = Header("", max_length=100),
) -> LLMChoice:
    return LLMChoice(x_llm_provider.strip().lower(), x_llm_key.strip(), x_llm_model.strip())


app = FastAPI(title="Neraca Fakta (Fact Ledger)", version=__version__)
app.include_router(whatsapp.router)
app.add_middleware(  # Vite dev server
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health(checker: Checker = Depends(get_checker)) -> dict:
    s = checker.settings
    info = {
        "status": "ok",
        "version": __version__,
        "data_source": checker.source.name,
        "demo": s.demo_mode,
        "llm_default": s.default_llm_provider,
        # Chat channels the UI can link to (no secrets, just whether they're set up).
        "bots": {
            "telegram": s.telegram_bot_username or None,
            "whatsapp": s.whatsapp_display_number or None,
        },
        "allow_user_keys": s.allow_user_keys,
        # Which providers the server can run on its own keys. Keys themselves never leave.
        "providers": [
            {"id": p.id, "label": p.label, "key_prefix": p.key_prefix,
             "default_model": s.llm_models.get(p.id) or p.default_model,
             "server_key": bool(s.llm_keys.get(p.id))}
            for p in PROVIDERS.values()
        ],
    }
    if isinstance(checker.source, FixtureSource):
        info["offline_tickers"] = checker.source.available()
    else:
        info["credits_spent"] = checker.source.credits_spent()
        info["credit_cap"] = s.credit_hard_cap
    return info


@app.post("/api/check", response_model=CheckResult)
def check(req: CheckRequest, llm: LLMChoice = Depends(llm_choice),
          checker: Checker = Depends(get_checker)) -> CheckResult:
    message = req.message.strip()
    if not message:
        raise HTTPException(422, "Pesan kosong.")
    try:
        return checker.check(message, llm)
    except LLMConfigError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/market", response_model=MarketSnapshot | None)
def market(service: MarketService | None = Depends(get_market)) -> MarketSnapshot | None:
    """Side-panel data. Backed by the SQLite cache, so polling costs credits only on expiry."""
    return service.snapshot() if service else None


@app.get("/api/watchlist", response_model=list[WatchQuote])
def watchlist(symbols: str = Query("", max_length=60, description="Comma-separated IDX codes, max 5"),
              service: MarketService | None = Depends(get_market)) -> list[WatchQuote]:
    """A viewer's own watchlist. Each new symbol costs 1 credit (cached 6h, within the panel reserve)."""
    if not service:
        return []
    wanted = [s for s in symbols.split(",") if s.strip()][:WATCHLIST_MAX]
    return service.watchlist(wanted)


@app.post("/api/check-media", response_model=CheckResult)
async def check_media(message: str = Form("", max_length=MAX_MESSAGE_CHARS),
                      files: list[UploadFile] = File(default=[]),
                      llm: LLMChoice = Depends(llm_choice),
                      checker: Checker = Depends(get_checker)) -> CheckResult:
    """A message plus up to 3 screenshots (PNG, JPEG, WebP, GIF; 5 MB each)."""
    if len(files) > MAX_IMAGES:
        raise HTTPException(422, f"Maksimal {MAX_IMAGES} gambar.")
    images = []
    for f in files:
        if f.content_type not in IMAGE_TYPES:
            raise HTTPException(415, "Hanya gambar PNG, JPEG, WebP, atau GIF.")
        data = await f.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Gambar maksimal 5 MB.")
        images.append(Image(data=data, mime=f.content_type))
    if not message.strip() and not images:
        raise HTTPException(422, "Pesan kosong.")
    try:
        # The pipeline is synchronous (network calls); keep it off the event loop.
        return await run_in_threadpool(checker.check, message.strip(), llm, images)
    except LLMConfigError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/llm/test")
def llm_test(llm: LLMChoice = Depends(llm_choice), checker: Checker = Depends(get_checker)) -> dict:
    """One small extraction call to confirm a provider + key + model works."""
    try:
        extractor = checker.extractor_for(llm)
    except LLMConfigError as e:
        raise HTTPException(400, str(e)) from e
    if extractor.name == "rules":
        return {"ok": True, "provider": "rules", "model": None}
    try:
        claims = extractor.extract(TEST_MESSAGE)
    except LLMError as e:
        return {"ok": False, "provider": extractor.name, "model": extractor.model,
                "error": llm_error_text(e, extractor)}
    return {"ok": True, "provider": extractor.name, "model": extractor.model, "claims_found": len(claims)}


_dist = ROOT / "web" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
