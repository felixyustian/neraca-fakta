"""LLM claim extraction: Anthropic (Claude), OpenAI, or Google Gemini.

All three get the same prompt and the same output schema (ExtractedClaims) and return
list[Claim]. The LLM only reads the message; verdicts come from verify.py.

Keys come from the server's .env, or from the user per request (the web UI's
"Kunci API" dialog). A per-request key is used for that call only and never stored.
"""
from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from .schema import Claim, ClaimType

SYSTEM_PROMPT = """\
You extract factual claims from Indonesian stock tips (WhatsApp/Telegram forwards) so they \
can be checked against reported IDX financial data. Read the message and return every claim.

Claim types:
- revenue_growth: pendapatan/penjualan/omzet naik or turun by a percentage
- profit_growth: laba/profit/earnings naik or turun by a percentage
- net_income: an absolute laba bersih amount in IDR
- dividend_yield: dividend yield in percent
- market_cap: kapitalisasi pasar / market cap in IDR
- unverifiable: anything else stated as fact or promise: price targets, "pasti naik", \
"ARA besok", insider rumours, bandar accumulation, recommendations. Give a short \
unverifiable_reason in Indonesian and the same reason in English in unverifiable_reason_en.

Rules:
- ticker: the 4-letter IDX code. Resolve well-known company names (Telkom -> TLKM, \
BCA -> BBCA, GoTo -> GOTO). If you cannot resolve it confidently, use the name in \
uppercase and mark the claim unverifiable.
- stated_value: the number as written, in its unit. "naik 200%" -> 200, unit pct. \
"Rp 5 T" / "5 triliun" -> 5000000000000, unit idr. Percentages stay positive; put the \
sign in direction ("up" / "down").
- period: copy what the message says ("Q2 2026", "YoY", "QoQ", "2025"); null if unstated.
- source_text: the exact span from the message the claim came from.
- Do not invent claims the message does not make. Do not judge whether they are true.
"""


# Output schema for every provider. No defaults and every field required: OpenAI's strict
# mode and Gemini's schema subset both need that. Converted to schema.Claim afterwards.
class ExtractedClaim(BaseModel):
    ticker: str = Field(description="IDX code, e.g. 'BBRI'")
    claim_type: ClaimType
    stated_value: float | None = Field(description="200 for 'naik 200%'; null if no number")
    unit: Literal["pct", "idr", "none"]
    direction: Literal["up", "down"] | None
    period: str | None = Field(description="'Q2 2026', 'YoY', 'QoQ', '2025', or null")
    source_text: str = Field(description="Exact span from the message")
    unverifiable_reason: str | None = Field(description="Indonesian; unverifiable claims only")
    unverifiable_reason_en: str | None = Field(description="English; unverifiable claims only")


class ExtractedClaims(BaseModel):
    claims: list[ExtractedClaim]


class ExtractedPost(BaseModel):
    """Output when screenshots or a video are attached: what was read, plus the claims."""
    media_text: str = Field(description="Faithful transcription of the text/speech in the attached media, "
                                        "original language; empty if none")
    claims: list[ExtractedClaim]


MEDIA_PROMPT = """
Screenshots of social media posts, chats or articles, or a video, may be attached. Read all
visible text (and, for video, what is said and shown). Put a faithful transcription in
media_text, in the original language, keeping the parts that make claims about stocks (at most
about 3000 characters). Extract claims from the message and the media together; source_text
must quote the message or media_text."""


@dataclass(frozen=True)
class Image:
    data: bytes
    mime: str


ProviderId = Literal["anthropic", "openai", "gemini"]


@dataclass(frozen=True)
class ProviderInfo:
    id: ProviderId
    label: str
    default_model: str
    env_key: str
    key_prefix: str  # for a friendly "this doesn't look like a ... key" hint in the UI


PROVIDERS: dict[str, ProviderInfo] = {
    p.id: p for p in [
        ProviderInfo("anthropic", "Anthropic (Claude)", "claude-opus-5", "ANTHROPIC_API_KEY", "sk-ant-"),
        ProviderInfo("openai", "OpenAI", "gpt-5-mini", "OPENAI_API_KEY", "sk-"),
        ProviderInfo("gemini", "Google Gemini", "gemini-2.5-flash", "GEMINI_API_KEY", "AI"),
    ]
}


class LLMError(RuntimeError):
    """Provider call failed. `kind` drives the message shown to the user."""

    def __init__(self, kind: Literal["auth", "rate_limit", "bad_request", "unavailable", "empty"],
                 detail: str = ""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def _status_of(e: Exception) -> int | None:
    for attr in ("status_code", "code", "status"):
        v = getattr(e, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(e, "response", None)
    return getattr(resp, "status_code", None)


def _classify(e: Exception) -> LLMError:
    status = _status_of(e)
    if status in (401, 403):
        return LLMError("auth", str(status))
    if status == 429:
        return LLMError("rate_limit", "429")
    if status in (400, 404, 422):
        return LLMError("bad_request", f"{status}: {str(e)[:200]}")
    return LLMError("unavailable", f"{type(e).__name__}: {str(e)[:200]}")


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref/$defs into one self-contained schema (Gemini's schema subset is stricter)."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class LLMExtractor:
    def __init__(self, provider: str, api_key: str, model: str | None = None):
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}")
        if not api_key:
            raise ValueError(f"No API key for {provider}")
        self.name = provider
        self.model = model or PROVIDERS[provider].default_model
        self._api_key = api_key

    def extract(self, message: str) -> list[Claim]:
        call = {"anthropic": self._anthropic, "openai": self._openai, "gemini": self._gemini}[self.name]
        try:
            result = call(message)
        except LLMError:
            raise
        except Exception as e:  # SDK-specific errors, normalized for the pipeline and the UI
            raise _classify(e) from e
        if result is None:
            raise LLMError("empty", "no parsed output")
        return [Claim(**c.model_dump()) for c in result.claims]

    def extract_media(self, message: str, images: list[Image], video_url: str | None = None
                      ) -> tuple[list[Claim], str]:
        """Claims from text plus screenshots (all providers) and a YouTube video (Gemini only)."""
        if video_url and self.name != "gemini":
            raise ValueError("Only Gemini can analyse YouTube videos")
        call = {"anthropic": self._anthropic_media, "openai": self._openai_media, "gemini": self._gemini_media}[self.name]
        try:
            result = call(message or "(no text, see attachments)", images, video_url)
        except LLMError:
            raise
        except Exception as e:
            raise _classify(e) from e
        if result is None:
            raise LLMError("empty", "no parsed output")
        return [Claim(**c.model_dump()) for c in result.claims], result.media_text

    def _anthropic_media(self, message: str, images: list[Image], _video: str | None) -> ExtractedPost | None:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key, max_retries=2, timeout=90.0)
        content = [{"type": "image", "source": {"type": "base64", "media_type": im.mime,
                                                "data": base64.standard_b64encode(im.data).decode()}}
                   for im in images] + [{"type": "text", "text": message}]
        response = client.beta.messages.parse(
            model=self.model,
            max_tokens=8192,
            system=SYSTEM_PROMPT + MEDIA_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_format=ExtractedPost,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            raise LLMError("empty", "refusal")
        return response.parsed_output

    def _openai_media(self, message: str, images: list[Image], _video: str | None) -> ExtractedPost | None:
        import openai

        client = openai.OpenAI(api_key=self._api_key, max_retries=2, timeout=90.0)
        content = [{"type": "input_image",
                    "image_url": f"data:{im.mime};base64,{base64.standard_b64encode(im.data).decode()}"}
                   for im in images] + [{"type": "input_text", "text": message}]
        response = client.responses.parse(
            model=self.model,
            instructions=SYSTEM_PROMPT + MEDIA_PROMPT,
            input=[{"role": "user", "content": content}],
            text_format=ExtractedPost,
        )
        return response.output_parsed

    def _gemini_media(self, message: str, images: list[Image], video_url: str | None) -> ExtractedPost | None:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key, http_options=types.HttpOptions(timeout=180_000))
        parts = [types.Part.from_bytes(data=im.data, mime_type=im.mime) for im in images]
        if video_url:
            parts.append(types.Part(file_data=types.FileData(file_uri=video_url)))
        parts.append(types.Part(text=message))
        response = client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT + MEDIA_PROMPT,
                response_mime_type="application/json",
                response_json_schema=_inline_refs(ExtractedPost.model_json_schema()),
                # Low resolution keeps long videos affordable; text in frames is still legible.
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if video_url else None,
            ),
        )
        if not response.text:
            return None
        return ExtractedPost.model_validate_json(response.text)

    def _anthropic(self, message: str) -> ExtractedClaims | None:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key, max_retries=2, timeout=60.0)
        response = client.beta.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            output_format=ExtractedClaims,
            output_config={"effort": "low"},
            # On a safety refusal, the API reruns the request on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            raise LLMError("empty", "refusal")
        return response.parsed_output

    def _openai(self, message: str) -> ExtractedClaims | None:
        import openai

        client = openai.OpenAI(api_key=self._api_key, max_retries=2, timeout=60.0)
        response = client.responses.parse(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=message,
            text_format=ExtractedClaims,
        )
        return response.output_parsed

    def _gemini(self, message: str) -> ExtractedClaims | None:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key,
                              http_options=types.HttpOptions(timeout=60_000))
        response = client.models.generate_content(
            model=self.model,
            contents=message,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=_inline_refs(ExtractedClaims.model_json_schema()),
            ),
        )
        if not response.text:
            return None
        return ExtractedClaims.model_validate_json(response.text)
