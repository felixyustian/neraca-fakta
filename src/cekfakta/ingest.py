"""Read the content behind links in a message: web articles, blogs, YouTube, TikTok, and
social posts (Instagram, Threads, Facebook, X).

What each platform allows without a login or paid key (checked 26 Sep 2026):
- Web / blogs: the page itself (title, description, article paragraphs).
- YouTube: title and channel (oEmbed) and the full description (watch page). Subtitles now
  need a browser proof-of-origin token, so the spoken content is only read when the user
  picks Gemini, which watches public YouTube videos natively (see llm.py).
- TikTok: the caption via the official oEmbed endpoint (rate-limited at times).
- Instagram, Threads, Facebook, X: mostly behind login walls. We read the page's public
  preview (og:description) when there is one; otherwise the user is asked for a screenshot.

Fetching is SSRF-safe: http(s) only, standard ports, every hop (redirects included) must
resolve to public IP addresses, with a size cap and a timeout.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from .schema import Platform, Source, SourceInfo, Text

log = logging.getLogger(__name__)

MAX_URLS = 3
MAX_BYTES = 3_000_000
MAX_TEXT_CHARS = 12_000
TIMEOUT_S = 10.0
MAX_REDIRECTS = 4
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


_URL_RE = re.compile(r"https?://[^\s<>\"'）)\]]+", re.I)
_HOSTS: list[tuple[Platform, tuple[str, ...]]] = [
    ("youtube", ("youtube.com", "youtu.be")),
    ("tiktok", ("tiktok.com",)),
    ("instagram", ("instagram.com",)),
    ("threads", ("threads.net", "threads.com")),
    ("facebook", ("facebook.com", "fb.watch", "fb.com")),
    ("x", ("x.com", "twitter.com")),
]
# Page previews that are login prompts, not the post.
_LOGIN_WALL = re.compile(r"log ?in|sign ?up|masuk|daftar|create an account|see (instagram|posts)", re.I)


def find_urls(text: str) -> list[str]:
    urls = []
    for m in _URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?")
        if u not in urls:
            urls.append(u)
    return urls[:MAX_URLS]


def strip_urls(text: str) -> str:
    return _URL_RE.sub(" ", text or "").strip()


def platform_of(url: str) -> Platform:
    host = (urlparse(url).hostname or "").lower()
    for platform, domains in _HOSTS:
        if any(host == d or host.endswith("." + d) for d in domains):
            return platform
    return "web"


# --- safe fetching -------------------------------------------------------------

class UnsafeURL(ValueError):
    pass


Resolver = Callable[[str], list[str]]


def _resolve(host: str) -> list[str]:
    return list({ai[4][0] for ai in socket.getaddrinfo(host, None)})


class Fetcher:
    def __init__(self, transport: httpx.BaseTransport | None = None, resolver: Resolver = _resolve):
        self.http = httpx.Client(timeout=TIMEOUT_S, transport=transport, follow_redirects=False,
                                 headers={"User-Agent": UA, "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"})
        self.resolver = resolver

    def check_url(self, url: str) -> None:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise UnsafeURL("only http(s) URLs")
        if p.port not in (None, 80, 443):
            raise UnsafeURL("non-standard port")
        try:
            ips = self.resolver(p.hostname)
        except OSError as e:
            raise UnsafeURL(f"cannot resolve {p.hostname}") from e
        for ip in ips:
            addr = ipaddress.ip_address(ip)
            if not addr.is_global or addr.is_multicast:
                raise UnsafeURL("address is not public")

    def get(self, url: str, accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5") -> tuple[str, str, str]:
        """(final_url, content_type, text). Follows redirects, re-checking every hop."""
        for _ in range(MAX_REDIRECTS + 1):
            self.check_url(url)
            with self.http.stream("GET", url, headers={"Accept": accept}) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                resp.raise_for_status()
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
                ctype = resp.headers.get("content-type", "")
                return url, ctype, raw.decode(resp.encoding or "utf-8", errors="replace")
        raise UnsafeURL("too many redirects")


# --- HTML extraction ---------------------------------------------------------------

class _PageParser(HTMLParser):
    """Title, meta previews, and readable paragraphs (article first, else body)."""
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button"}
    BLOCKS = {"p", "h1", "h2", "h3", "li", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self._skip = 0
        self._article = 0
        self._block: list[str] | None = None
        self.body_blocks: list[str] = []
        self.article_blocks: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
        elif tag == "title":
            self._in_title = True
        elif tag in self.SKIP:
            self._skip += 1
        elif tag == "article":
            self._article += 1
        elif tag in self.BLOCKS and not self._skip:
            self._block = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "article" and self._article:
            self._article -= 1
        elif tag in self.BLOCKS and self._block is not None:
            text = re.sub(r"\s+", " ", "".join(self._block)).strip()
            if len(text) >= 30 or (tag.startswith("h") and len(text) >= 8):
                (self.article_blocks if self._article else self.body_blocks).append(text)
            self._block = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._block is not None and not self._skip:
            self._block.append(data)


def parse_page(html: str) -> tuple[dict[str, str], str, str]:
    """(meta, title, readable text)."""
    p = _PageParser()
    try:
        p.feed(html)
    except Exception:  # malformed HTML: keep what was parsed
        pass
    blocks = p.article_blocks or p.body_blocks
    seen, out = set(), []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return p.meta, re.sub(r"\s+", " ", p.title).strip(), "\n".join(out)[:MAX_TEXT_CHARS]


def _note(id_: str, en: str) -> Text:
    return Text(id=id_, en=en)


SCREENSHOT_NOTE = _note(
    "Konten ini tidak bisa dibaca tanpa login. Unggah tangkapan layar atau tempel teksnya.",
    "This content can't be read without logging in. Upload a screenshot or paste the text.",
)


# --- platform readers ----------------------------------------------------------------

def _youtube_id(url: str) -> str | None:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host.endswith("youtu.be"):
        return p.path.strip("/").split("/")[0] or None
    if "watch" in p.path:
        return (parse_qs(p.query).get("v") or [None])[0]
    m = re.match(r"/(shorts|live|embed)/([\w-]{6,})", p.path)
    return m.group(2) if m else None


def read_youtube(f: Fetcher, url: str) -> Source:
    vid = _youtube_id(url)
    if not vid:
        return Source(url=url, platform="youtube", status="error",
                      note=_note("Tautan YouTube tidak dikenali.", "Unrecognised YouTube link."))
    watch = f"https://www.youtube.com/watch?v={vid}"
    title = author = None
    try:
        _, _, body = f.get(f"https://www.youtube.com/oembed?url={watch}&format=json", accept="application/json")
        oe = json.loads(body)
        title, author = oe.get("title"), oe.get("author_name")
    except (httpx.HTTPError, ValueError):
        pass
    description = ""
    try:
        _, _, html = f.get(watch)
        m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*(?:var |</script>)", html, re.S)
        if m:
            details = json.loads(m.group(1)).get("videoDetails", {})
            description = details.get("shortDescription", "")
            title = title or details.get("title")
            author = author or details.get("author")
    except (httpx.HTTPError, ValueError):
        pass
    if not title and not description:
        return Source(url=url, platform="youtube", status="error", video_url=watch,
                      note=_note("Video tidak bisa dibaca (privat atau dihapus?).", "Couldn't read the video (private or removed?)."))
    return Source(
        url=url, platform="youtube", status="partial", title=title, author=author, video_url=watch,
        text="\n".join(x for x in [title, description] if x)[:MAX_TEXT_CHARS],
        note=_note("Dibaca dari judul dan deskripsi. Pilih Gemini di pengaturan AI untuk menganalisis isi ucapan video.",
                   "Read from the title and description. Choose Gemini in AI settings to analyse what's said in the video."),
    )


def read_tiktok(f: Fetcher, url: str) -> Source:
    try:
        _, _, body = f.get(f"https://www.tiktok.com/oembed?url={url}", accept="application/json")
        oe = json.loads(body)
        if oe.get("title"):
            return Source(url=url, platform="tiktok", status="partial", title=oe["title"][:120],
                          author=oe.get("author_name"), text=oe["title"],
                          note=_note("Dibaca dari keterangan video. Isi ucapan video tidak dianalisis.",
                                     "Read from the video caption. Speech in the video isn't analysed."))
    except (httpx.HTTPError, ValueError):
        pass
    return read_social(f, url, "tiktok")


def read_social(f: Fetcher, url: str, platform: Platform) -> Source:
    """Instagram, Threads, Facebook, X, and TikTok fallback: the public preview, if any."""
    try:
        _, _, html = f.get(url)
        meta, title, _ = parse_page(html)
    except (httpx.HTTPError, UnsafeURL) as e:
        log.info("Social fetch failed for %s: %s", url, e)
        return Source(url=url, platform=platform, status="blocked", note=SCREENSHOT_NOTE)
    desc = meta.get("og:description") or meta.get("description") or meta.get("twitter:description") or ""
    if len(desc) < 25 or _LOGIN_WALL.search(desc[:80]):
        return Source(url=url, platform=platform, status="blocked", note=SCREENSHOT_NOTE)
    return Source(url=url, platform=platform, status="partial", title=meta.get("og:title") or title or None,
                  text=desc[:MAX_TEXT_CHARS],
                  note=_note("Dibaca dari pratinjau publik postingan; bisa terpotong.",
                             "Read from the post's public preview; it may be truncated."))


def read_web(f: Fetcher, url: str) -> Source:
    final, ctype, body = f.get(url)
    if "html" not in ctype and "text/plain" not in ctype:
        return Source(url=url, platform="web", status="error",
                      note=_note("Jenis konten ini belum didukung (hanya halaman web).",
                                 "This content type isn't supported yet (web pages only)."))
    if "text/plain" in ctype:
        return Source(url=final, platform="web", status="ok", text=body[:MAX_TEXT_CHARS])
    meta, title, text = parse_page(body)
    title = meta.get("og:title") or title or None
    desc = meta.get("og:description") or meta.get("description") or ""
    content = text or desc
    if not content:
        return Source(url=final, platform="web", status="blocked", title=title, note=SCREENSHOT_NOTE)
    if title and content.startswith(title):  # the headline is usually repeated as the first <h1>
        title_line = None
    else:
        title_line = title
    return Source(url=final, platform="web", status="ok", title=title,
                  author=meta.get("author") or meta.get("og:site_name"),
                  text="\n".join(x for x in [title_line, content] if x)[:MAX_TEXT_CHARS])


def read_source(url: str, fetcher: Fetcher | None = None) -> Source:
    f = fetcher or Fetcher()
    platform = platform_of(url)
    try:
        if platform == "youtube":
            return read_youtube(f, url)
        if platform == "tiktok":
            return read_tiktok(f, url)
        if platform != "web":
            return read_social(f, url, platform)
        return read_web(f, url)
    except UnsafeURL:
        return Source(url=url, platform=platform, status="error",
                      note=_note("Tautan ini tidak diizinkan.", "This link isn't allowed."))
    except httpx.HTTPStatusError as e:
        status = "blocked" if e.response.status_code in (401, 403, 429) else "error"
        return Source(url=url, platform=platform, status=status,
                      note=SCREENSHOT_NOTE if status == "blocked" else
                      _note(f"Halaman tidak bisa dibuka (HTTP {e.response.status_code}).",
                            f"Couldn't open the page (HTTP {e.response.status_code})."))
    except httpx.HTTPError:
        return Source(url=url, platform=platform, status="error",
                      note=_note("Halaman tidak bisa dihubungi.", "Couldn't reach the page."))
