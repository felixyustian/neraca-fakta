"""Reading links (web, YouTube, TikTok, social) and screenshots. All network is mocked."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from cekfakta import api
from cekfakta.config import Settings
from cekfakta.facts import FixtureSource
from cekfakta.ingest import Fetcher, UnsafeURL, find_urls, parse_page, platform_of, read_source, strip_urls
from cekfakta.llm import LLMExtractor
from cekfakta.pipeline import Checker, LLMChoice
from cekfakta.schema import Claim, ClaimType

ARTICLE = """<html><head><title>GOTO naik</title>
<meta property="og:title" content="Laba GOTO melonjak"><meta name="author" content="Redaksi"></head>
<body><nav><p>Menu utama navigasi yang panjang sekali untuk diabaikan</p></nav>
<article><h1>Laba GOTO melonjak</h1>
<p>Emiten teknologi GOTO melaporkan laba naik 200% YoY pada kuartal kedua tahun ini.</p>
<script>var tracking = "abaikan skrip ini sepenuhnya ya";</script>
<p>Pendapatan tumbuh 30% dibanding periode yang sama tahun lalu, menurut laporan resmi.</p></article>
<footer><p>Hak cipta dilindungi undang-undang, semua hak dilindungi.</p></footer></body></html>"""

YT_PAGE = ('<html><script>var ytInitialPlayerResponse = {"videoDetails": {"title": "Saham GOTO", '
           '"author": "Kanal Saham", "shortDescription": "TLKM laba naik 20% YoY, wajib beli!"}};var x=1;</script></html>')


def public(_host):
    return ["93.184.216.34"]


def fetcher(routes: dict[str, httpx.Response | callable], resolver=public):
    def handler(req: httpx.Request):
        for prefix, resp in routes.items():
            if str(req.url).startswith(prefix):
                return resp(req) if callable(resp) else resp
        return httpx.Response(404)
    return Fetcher(transport=httpx.MockTransport(handler), resolver=resolver)


def html(body, status=200):
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


# --- parsing & safety -------------------------------------------------------------

def test_url_helpers():
    msg = "Cek ini https://investor.id/a/1, dan https://youtu.be/abc123. lalu https://x.com/u/status/1)"
    assert find_urls(msg) == ["https://investor.id/a/1", "https://youtu.be/abc123", "https://x.com/u/status/1"]
    assert "http" not in strip_urls(msg)
    assert [platform_of(u) for u in ["https://m.youtube.com/watch?v=1", "https://vt.tiktok.com/Z",
            "https://www.threads.com/@a/post/1", "https://web.facebook.com/p", "https://blog.example.com"]] == \
        ["youtube", "tiktok", "threads", "facebook", "web"]


@pytest.mark.parametrize("url,ips", [
    ("http://127.0.0.1/", ["127.0.0.1"]),
    ("http://internal.example/", ["10.0.0.5"]),
    ("http://metadata.example/", ["169.254.169.254"]),
    ("http://v6.example/", ["::1"]),
    ("file:///etc/passwd", ["93.184.216.34"]),
    ("https://example.com:8080/", ["93.184.216.34"]),
])
def test_unsafe_urls_rejected(url, ips):
    with pytest.raises(UnsafeURL):
        Fetcher(resolver=lambda _h: ips).check_url(url)


def test_redirect_to_private_address_is_blocked():
    f = fetcher({"https://short.example/": httpx.Response(302, headers={"location": "http://admin.local/"})},
                resolver=lambda h: ["192.168.1.1"] if h == "admin.local" else ["93.184.216.34"])
    src = read_source("https://short.example/x", f)
    assert src.status == "error" and "allowed" in src.note.en


def test_parse_page_prefers_article_and_skips_chrome():
    meta, title, text = parse_page(ARTICLE)
    assert meta["og:title"] == "Laba GOTO melonjak" and title == "GOTO naik"
    assert "laba naik 200% YoY" in text and "Pendapatan tumbuh 30%" in text
    assert "Menu utama" not in text and "tracking" not in text and "Hak cipta" not in text


# --- platform readers -------------------------------------------------------------

def test_read_web_article():
    src = read_source("https://news.example/goto", fetcher({"https://news.example/": html(ARTICLE)}))
    assert (src.platform, src.status, src.title, src.author) == ("web", "ok", "Laba GOTO melonjak", "Redaksi")
    assert src.text.startswith("Laba GOTO melonjak\n")


def test_read_youtube_title_description():
    f = fetcher({
        "https://www.youtube.com/oembed": httpx.Response(200, json={"title": "Saham GOTO", "author_name": "Kanal Saham"}),
        "https://www.youtube.com/watch": html(YT_PAGE),
    })
    src = read_source("https://youtu.be/abc123?si=x", f)
    assert (src.status, src.author, src.video_url) == ("partial", "Kanal Saham", "https://www.youtube.com/watch?v=abc123")
    assert "TLKM laba naik 20% YoY" in src.text and "Gemini" in src.note.en


def test_read_tiktok_caption_and_social_login_wall():
    f = fetcher({"https://www.tiktok.com/oembed": httpx.Response(200, json={"title": "BBCA dividen yield 12% cuy", "author_name": "cuan"})})
    tt = read_source("https://www.tiktok.com/@cuan/video/1", f)
    assert (tt.status, tt.text, tt.author) == ("partial", "BBCA dividen yield 12% cuy", "cuan")

    wall = '<meta property="og:description" content="Log in to see photos and videos from friends.">'
    ig = read_source("https://www.instagram.com/p/xyz/", fetcher({"https://www.instagram.com/": html(wall)}))
    assert ig.status == "blocked" and "screenshot" in ig.note.en

    post = '<meta property="og:description" content="TLKM laba bersih kuartal ini Rp 6,3 triliun, mantap sekali">'
    th = read_source("https://www.threads.net/@a/post/1", fetcher({"https://www.threads.net/": html(post)}))
    assert th.status == "partial" and "Rp 6,3 triliun" in th.text

    fb = read_source("https://www.facebook.com/p/1", fetcher({"https://www.facebook.com/": html("", 403)}))
    assert fb.status == "blocked"


# --- pipeline ---------------------------------------------------------------------

def settings(tmp_path, **kw):
    return Settings(sectors_api_key="", sectors_base_url="", cache_path=tmp_path / "c.sqlite", credit_hard_cap=0,
                    credit_offset=0, data_source="fixtures", fixtures_dir=tmp_path, **kw)


def test_link_content_is_fact_checked(fixture_dir):
    c = Checker(settings(fixture_dir), FixtureSource(fixture_dir))
    page = ARTICLE.replace("GOTO", "TLKM").replace("200%", "20%")
    c.fetcher = fetcher({"https://news.example/": html(page)})
    r = c.check("Beneran? https://news.example/tlkm", LLMChoice("rules"))
    assert [s.platform for s in r.sources] == ["web"] and r.sources[0].chars > 50
    assert r.verdicts[0].claim.ticker == "TLKM" and r.verdicts[0].label.value == "Sesuai data"
    assert r.message == "Beneran? https://news.example/tlkm"


def test_screenshots_without_ai_add_a_note(fixture_dir):
    from cekfakta.llm import Image
    c = Checker(settings(fixture_dir), FixtureSource(fixture_dir))
    r = c.check("TLKM laba naik 20%", LLMChoice("rules"), [Image(b"png", "image/png")])
    assert r.extractor == "rules" and "AI" in r.notes[0].en


def test_gemini_gets_youtube_video_and_screenshot(fixture_dir, monkeypatch):
    seen = {}

    def fake_media(self, message, images, video_url=None):
        seen.update(message=message, images=len(images), video=video_url)
        return [Claim(ticker="TLKM", claim_type=ClaimType.PROFIT_GROWTH, stated_value=20, unit="pct",
                      direction="up", source_text="laba TLKM naik 20%")], "Di video: laba TLKM naik 20%"

    monkeypatch.setattr(LLMExtractor, "extract_media", fake_media)
    from cekfakta.llm import Image
    c = Checker(settings(fixture_dir), FixtureSource(fixture_dir))
    c.fetcher = fetcher({"https://www.youtube.com/oembed": httpx.Response(200, json={"title": "Saham"}),
                         "https://www.youtube.com/watch": html(YT_PAGE)})
    r = c.check("https://www.youtube.com/watch?v=abc123", LLMChoice("gemini", "k"), [Image(b"png", "image/png")])
    assert seen["video"] == "https://www.youtube.com/watch?v=abc123" and seen["images"] == 1
    assert "TLKM laba naik 20% YoY" in seen["message"]  # description passed as text too
    assert r.sources[0].analyzed_video and r.media_text == "Di video: laba TLKM naik 20%"
    # Other providers don't get the video, only its title and description.
    seen.clear()
    monkeypatch.setattr(LLMExtractor, "extract", lambda self, m: [])
    c.check("https://youtu.be/abc123", LLMChoice("openai", "k"))
    assert seen == {}


# --- upload API -------------------------------------------------------------------

def test_check_media_endpoint_limits(fixture_dir):
    s = settings(fixture_dir)
    api.app.dependency_overrides[api.get_checker] = lambda: Checker(s, FixtureSource(fixture_dir))
    c = TestClient(api.app)
    png = ("s.png", b"\x89PNG....", "image/png")
    ok = c.post("/api/check-media", data={"message": "TLKM laba naik 20% YoY"}, files=[("files", png)],
                headers={"X-LLM-Provider": "rules"})
    assert ok.status_code == 200 and "AI" in ok.json()["notes"][0]["en"]
    assert c.post("/api/check-media", files=[("files", ("a.pdf", b"%PDF", "application/pdf"))]).status_code == 415
    assert c.post("/api/check-media", files=[("files", png)] * 4).status_code == 422
    big = ("b.png", b"0" * (5 * 1024 * 1024 + 1), "image/png")
    assert c.post("/api/check-media", files=[("files", big)]).status_code == 413
    assert c.post("/api/check-media", data={"message": " "}).status_code == 422
