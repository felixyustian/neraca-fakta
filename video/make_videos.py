"""Build the teaser (~60 s) and judging (<= 3 min) videos from the running app.

    python video/make_videos.py [teaser|judging|all]

Needs: the app running (default http://localhost:8000, offline data is fine), ffmpeg,
macOS `say` with the Indonesian voice "Damayanti", and Playwright (`pip install playwright`,
`python -m playwright install chromium`).

Pipeline per segment: TTS narration -> measure -> record the scene for exactly that long
(headless Chromium screencast, with a visible cursor) -> overlay subtitle images -> mix.
Outputs in video/out/: MP4s, .srt subtitles (id, en), thumbnails, and YouTube metadata.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page, async_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import cards  # noqa: E402
from segments import DEMO_MESSAGE, JUDGING, LINK_MESSAGE, TEASER  # noqa: E402

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
BUILD = HERE / "build"
OUT = HERE / "out"
VOICE = "Damayanti"
LEAD, TAIL = 0.35, 0.6  # silence before / after each narration line, seconds
FPS = 30
LIMITS = {"teaser": 60.0, "judging": 180.0}
# 1344x756 CSS px at 1.4286x -> 1920x1080 frames: ~15% larger text than 1536 wide, still the 3-column layout.
APP_VIEW = dict(viewport={"width": 1344, "height": 756}, device_scale_factor=1920 / 1344)
CARD_VIEW = dict(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)

CURSOR_JS = """
(() => {
  const init = () => {
    if (document.getElementById('__cursor')) return;
    const st = document.createElement('style');
    st.textContent = '::-webkit-scrollbar{width:0!important;height:0!important}' +
      '#__cursor{position:fixed;left:-50px;top:-50px;z-index:2147483647;pointer-events:none;transform:translate(-4px,-3px)}' +
      '.__ripple{position:fixed;z-index:2147483646;pointer-events:none;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;' +
      'background:rgba(20,184,166,.35);border:2px solid rgba(15,118,110,.8);animation:__rp .5s ease-out forwards}' +
      '@keyframes __rp{to{transform:scale(3.4);opacity:0}}';
    document.head.appendChild(st);
    const c = document.createElement('div'); c.id = '__cursor';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M4 2.5l7.2 18.6 2.7-7.7 7.6-2.6z" fill="#111" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', e => {
      const r = document.createElement('div'); r.className = '__ripple';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      document.body.appendChild(r); setTimeout(() => r.remove(), 600);
    }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
"""


def run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {res.stderr[-800:]}")
    return res.stdout


def duration(path: Path) -> float:
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


# --- narration & captions -----------------------------------------------------------

@dataclass
class Seg:
    idx: int
    scene: str
    id: str
    en: str
    wav: Path = None
    tts: float = 0.0
    captions: list[tuple[float, float, str, str]] = field(default_factory=list)  # (start, end, en, id)

    @property
    def dur(self) -> float:
        return round(LEAD + self.tts + TAIL, 2)


def tts(text: str, out: Path, rate: int) -> float:
    aiff = out.with_suffix(".aiff")
    run(["say", "-v", VOICE, "-r", str(rate), "-o", str(aiff), text])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ar", "48000", "-ac", "2", str(out)])
    aiff.unlink()
    return duration(out)


def split_caption(text: str, max_chars: int = 92) -> list[str]:
    """Split long lines at the punctuation nearest the middle, recursively."""
    if len(text) <= max_chars:
        return [text]
    mid = len(text) / 2
    cuts = [m.end() for m in re.finditer(r"[.:;!?,]\s", text)]
    if not cuts:
        cuts = [m.start() for m in re.finditer(r"\s", text)]
    cut = min(cuts, key=lambda c: abs(c - mid))
    return split_caption(text[:cut].strip(), max_chars) + split_caption(text[cut:].strip(), max_chars)


def split_into(text: str, n: int) -> list[str]:
    """Exactly n caption parts (so both languages share timing): split finer, then merge the shortest pairs."""
    parts = [text]
    for max_chars in range(len(text), 15, -3):
        parts = split_caption(text, max_chars)
        if len(parts) >= n:
            break
    while len(parts) > n:
        i = min(range(len(parts) - 1), key=lambda k: len(parts[k]) + len(parts[k + 1]))
        parts[i:i + 2] = [parts[i] + " " + parts[i + 1]]
    return parts


def build_narration(kind: str, spec: list[dict]) -> list[Seg]:
    """TTS every line; speed up the voice if the video would exceed its limit."""
    work = BUILD / kind
    work.mkdir(parents=True, exist_ok=True)
    for rate in range(180, 231, 10):
        segs = []
        for i, s in enumerate(spec):
            seg = Seg(i, s["scene"], s["id"], s["en"])
            seg.wav = work / f"narr_{i:02d}.wav"
            seg.tts = tts(seg.id, seg.wav, rate)
            segs.append(seg)
        total = sum(s.dur for s in segs)
        print(f"  [{kind}] voice rate {rate}: {total:.1f}s (limit {LIMITS[kind]:.0f}s)")
        if total <= LIMITS[kind] - 1.5:
            break
    for seg in segs:
        n = max(len(split_caption(seg.en)), len(split_caption(seg.id)))
        en_parts, id_parts = split_into(seg.en, n), split_into(seg.id, n)
        weights = [len(p) for p in id_parts]
        t = LEAD
        for w, en, idt in zip(weights, en_parts, id_parts):
            span = seg.tts * w / sum(weights)
            seg.captions.append((round(t, 2), round(t + span, 2), en, idt))
            t += span
        # Hold the last caption through the tail so it doesn't flash off early.
        s0, _, en, idt = seg.captions[-1]
        seg.captions[-1] = (s0, round(seg.dur - 0.05, 2), en, idt)
    return segs


# --- recording ------------------------------------------------------------------------

class Recorder:
    """Screencast frames (only emitted when pixels change) plus a seed frame at t0."""

    def __init__(self, page: Page):
        self.page = page
        self.frames: list[tuple[float, bytes]] = []
        self.t0 = 0.0

    async def start(self):
        self.cdp = await self.page.context.new_cdp_session(self.page)

        def on_frame(params):
            self.frames.append((params["metadata"]["timestamp"], base64.b64decode(params["data"])))
            asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))

        self.cdp.on("Page.screencastFrame", on_frame)
        self.t0 = time.time()
        self.frames.append((self.t0, await self.page.screenshot(type="jpeg", quality=92)))
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                                      "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})

    def elapsed(self) -> float:
        return time.time() - self.t0

    async def until(self, t: float):
        """Wait until t seconds after the recording started."""
        wait = t - self.elapsed()
        if wait > 0:
            await asyncio.sleep(wait)

    async def stop(self, dur: float, out: Path):
        await self.until(dur + 0.1)
        await self.cdp.send("Page.stopScreencast")
        frames = sorted((ts - self.t0, data) for ts, data in self.frames if 0 <= ts - self.t0 <= dur)
        tmp = Path(tempfile.mkdtemp(dir=BUILD))
        lines = []
        for i, (ts, data) in enumerate(frames):
            f = tmp / f"f{i:05d}.jpg"
            f.write_bytes(data)
            nxt = frames[i + 1][0] if i + 1 < len(frames) else dur
            lines.append(f"file '{f}'\nduration {max(nxt - ts, 1 / 120):.4f}")
        lines.append(f"file '{tmp / f'f{len(frames) - 1:05d}.jpg'}'")
        (tmp / "list.txt").write_text("\n".join(lines))
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
             "-vf", f"scale=1920:1080:flags=lanczos,fps={FPS},format=yuv420p", "-t", f"{dur:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "16", str(out)])
        shutil.rmtree(tmp)
        print(f"    recorded {out.name}: {len(frames)} frames, {dur:.1f}s")


async def glide(page: Page, target, steps: int = 28, dx: float = 0.5, dy: float = 0.5):
    """Move the (visible) cursor smoothly to an element or (x, y)."""
    if isinstance(target, tuple):
        x, y = target
    else:
        await target.scroll_into_view_if_needed()
        box = await target.bounding_box()
        x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
    await page.mouse.move(x, y, steps=steps)
    return x, y


async def click(page: Page, target, steps: int = 26):
    await glide(page, target, steps)
    await asyncio.sleep(0.12)
    await page.mouse.down()
    await asyncio.sleep(0.06)
    await page.mouse.up()


async def scroll_to(page: Page, selector: str, offset: int = 90, smooth: bool = True, nth: int = 0):
    await page.evaluate(
        """([sel, off, smooth, nth]) => { const el = document.querySelectorAll(sel)[nth]; if (!el) return;
             const top = el.getBoundingClientRect().top + window.scrollY - off;
             window.scrollTo({ top, behavior: smooth ? 'smooth' : 'instant' }); }""",
        [selector, offset, smooth, nth])


async def open_app(page: Page):
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_selector(".side-left .hero-index-value")
    await page.wait_for_selector(".example")
    await page.mouse.move(768, 520)


async def run_check(page: Page, message: str = DEMO_MESSAGE):
    await page.fill("#msg", message)
    await page.click("button.primary.big")
    await page.wait_for_selector(".company .ticker-badge")
    await asyncio.sleep(1.2)  # entry animations settle


# Each scene: async (page, rec, dur). Setup runs before rec.start(); pacing uses rec.until().

async def scene_app_type(page, rec, dur):
    await rec.start()
    await rec.until(0.5)
    await click(page, page.locator("#msg"))
    delay = max(6, min(40, (dur - 2.3) * 1000 / len(DEMO_MESSAGE)))
    await page.keyboard.type(DEMO_MESSAGE, delay=delay)
    await glide(page, page.locator("button.primary.big"), steps=30)


async def scene_app_check(page, rec, dur):
    await page.fill("#msg", DEMO_MESSAGE)
    await scroll_to(page, ".input-card", 120, smooth=False)
    await page.mouse.move(900, 650)
    await rec.start()
    await rec.until(0.4)
    await click(page, page.locator("button.primary.big"))
    await page.wait_for_selector(".summary-card")
    await rec.until(dur * 0.62)
    await glide(page, page.locator(".summary-card .filters"), steps=30)


async def scene_app_verdicts(page, rec, dur):
    await run_check(page)
    await scroll_to(page, ".verdicts", 150, smooth=False)
    await asyncio.sleep(0.4)
    cardsel = page.locator(".verdict")
    n = await cardsel.count()
    await rec.start()
    order = [0, 1, 2, 3]
    for k, i in enumerate(order[:n]):
        await rec.until(0.3 + k * (dur - 0.8) / len(order))
        if k == 2:
            await scroll_to(page, ".verdict", 150, nth=2)
            await asyncio.sleep(0.5)
        await glide(page, cardsel.nth(i), steps=24, dy=0.62)


async def scene_app_highlight(page, rec, dur):
    await run_check(page)
    await scroll_to(page, ".verdict", 140, smooth=False, nth=2)  # the partial-match card with its gauge
    await asyncio.sleep(0.4)
    await rec.start()
    await rec.until(0.3)
    await glide(page, page.locator(".verdict").nth(2).locator(".gauge"), steps=26)
    await rec.until(dur * 0.42)
    await scroll_to(page, ".message-card", 120)
    await asyncio.sleep(0.6)
    mark = page.locator("mark.hl.st-unknown")
    await glide(page, mark, steps=26)
    await rec.until(dur * 0.66)
    await click(page, mark, steps=6)
    await asyncio.sleep(0.9)
    how = page.locator(".verdict.st-unknown .link-btn")
    if await how.count():
        await click(page, how.first, steps=22)


async def scene_app_company(page, rec, dur):
    await run_check(page)
    await scroll_to(page, ".company", 110, smooth=False, nth=1)  # TLKM: has dividends
    await asyncio.sleep(0.4)
    panel = page.locator(".company").nth(1)
    await rec.start()
    await rec.until(0.3)
    svg = panel.locator(".viz svg").first
    box = await svg.bounding_box()
    await page.mouse.move(box["x"] + 60, box["y"] + box["height"] * 0.5, steps=18)
    await page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.45, steps=40)
    await rec.until(dur * 0.36)
    await click(page, panel.locator(".tab").nth(1), steps=20)
    await asyncio.sleep(0.5)
    await glide(page, panel.locator(".viz rect[tabindex]").last, steps=22)
    await rec.until(dur * 0.68)
    await click(page, panel.locator(".tab").nth(2), steps=20)
    await asyncio.sleep(0.5)
    await glide(page, panel.locator(".viz rect[tabindex]").last, steps=22)


async def scene_app_markets(page, rec, dur):
    await page.mouse.move(700, 300)
    await rec.start()
    await rec.until(0.3)
    spark = page.locator(".side-left .spark svg").first
    box = await spark.bounding_box()
    await page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2, steps=20)
    await page.mouse.move(box["x"] + box["width"] - 10, box["y"] + box["height"] / 2, steps=36)
    await rec.until(dur * 0.45)
    await click(page, page.locator(".side-right .mini-tabs button").nth(1), steps=26)
    await rec.until(dur * 0.72)
    await glide(page, page.locator(".side-right .news-list a").first, steps=24)


async def scene_app_markets_custom(page, rec, dur):
    await page.mouse.move(700, 300)
    await rec.start()
    await rec.until(0.3)
    await glide(page, page.locator(".side-left .rows").first, steps=26)
    await rec.until(dur * 0.18)
    await click(page, page.locator(".side-left .customize-btn"), steps=24)
    await page.wait_for_selector("dialog.wide[open]")
    await rec.until(dur * 0.36)
    inp = page.locator("dialog.wide .key-row input")
    await click(page, inp, steps=20)
    await page.keyboard.type("BBCA", delay=90)
    await click(page, page.locator("dialog.wide .key-row button"), steps=14)
    await rec.until(dur * 0.58)
    sti = page.locator("dialog.wide .pick", has_text="STI")
    if await sti.count():
        await click(page, sti.first, steps=20)
    await rec.until(dur * 0.74)
    await click(page, page.locator("dialog.wide .dialog-actions .primary"), steps=24)
    await asyncio.sleep(0.8)
    await glide(page, page.locator(".watch li").first, steps=24)


async def scene_app_bilingual(page, rec, dur):
    await run_check(page)
    await scroll_to(page, ".summary-card", 110, smooth=False)
    await asyncio.sleep(0.3)
    await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    await page.mouse.move(900, 400)
    await rec.start()
    await rec.until(0.3)
    await click(page, page.locator(".seg-toggle button", has_text="EN").first, steps=28)
    await rec.until(dur * 0.5)
    await click(page, page.locator(".icon-btn.round"), steps=22)  # light -> dark
    await asyncio.sleep(0.4)
    await glide(page, (760, 560), steps=30)


async def scene_app_links(page, rec, dur):
    await page.mouse.move(800, 600)
    await rec.start()
    await rec.until(0.3)
    await click(page, page.locator("#msg"), steps=22)
    await page.keyboard.type(LINK_MESSAGE, delay=max(6, min(22, (dur * 0.25) * 1000 / len(LINK_MESSAGE))))
    await click(page, page.locator("button.primary.big"), steps=20)
    await page.wait_for_selector(".sources-card", timeout=30_000)
    await asyncio.sleep(0.6)
    await scroll_to(page, ".sources-card", 120)
    await asyncio.sleep(0.7)
    items = page.locator(".sources li")
    await glide(page, items.first, steps=22)
    await rec.until(dur * 0.72)
    if await items.count() > 1:
        await glide(page, items.nth(1), steps=22)
    await rec.until(dur * 0.86)
    await scroll_to(page, ".input-card", 100)
    await asyncio.sleep(0.6)
    await glide(page, page.locator(".attach-btn"), steps=24)


APP_SCENES = {
    "app_type": scene_app_type, "app_check": scene_app_check, "app_verdicts": scene_app_verdicts,
    "app_highlight": scene_app_highlight, "app_company": scene_app_company, "app_markets": scene_app_markets,
    "app_markets_custom": scene_app_markets_custom, "app_bilingual": scene_app_bilingual, "app_links": scene_app_links,
}


def bot_reply_text() -> str:
    """The real reply the chat bot core produces for the card's sample message (demo data)."""
    from dataclasses import replace
    from cekfakta.bot.core import ChatBot
    from cekfakta.bot.markup import WhatsAppText
    from cekfakta.config import load_settings
    from cekfakta.facts import make_source
    from cekfakta.pipeline import Checker
    from cekfakta.store import Store

    s = replace(load_settings(), data_source="fixtures", llm_provider="rules", demo_mode=False,
                cache_path=BUILD / "bot-cache.sqlite", public_app_url="")
    bot = ChatBot(Checker(s, make_source(s)), Store(s.cache_path), None, 99)
    text = bot.handle("wa:video", cards.reply_user_msg(), WhatsAppText())[0]
    text = text.replace("​", "").replace("*", "").replace("_", "")
    return text


async def record_segment(browser, seg: Seg, kind: str, bot_reply: str) -> Path:
    out = BUILD / kind / f"clip_{seg.idx:02d}.mp4"
    is_card = seg.scene.startswith("card_")
    ctx = await browser.new_context(**(CARD_VIEW if is_card else APP_VIEW), color_scheme="light", locale="id-ID")
    if not is_card:
        await ctx.add_init_script(CURSOR_JS)
        await ctx.add_init_script("""try { localStorage.setItem('cekfakta.theme','light');
          localStorage.setItem('cekfakta.lang','id'); localStorage.removeItem('cekfakta.panels'); } catch (e) {}""")
    page = await ctx.new_page()
    rec = Recorder(page)
    if is_card:
        html_doc = (cards.card_bots(seg.dur, bot_reply) if seg.scene == "card_bots"
                    else cards.CARDS[seg.scene](seg.dur))
        await page.set_content(html_doc, wait_until="load")
        await rec.start()
    else:
        await open_app(page)
        await APP_SCENES[seg.scene](page, rec, seg.dur)
    await rec.stop(seg.dur, out)
    await ctx.close()
    return out


async def render_png(browser, html_doc: str, out: Path, size=(1920, 1080), transparent=True):
    ctx = await browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    page = await ctx.new_page()
    await page.set_content(html_doc, wait_until="load")
    await page.screenshot(path=str(out), omit_background=transparent, type="png")
    await ctx.close()


# --- composition ------------------------------------------------------------------------

def compose_segment(seg: Seg, clip: Path, caption_pngs: list[Path], out: Path):
    inputs = ["-i", str(clip), "-i", str(seg.wav)]
    for p in caption_pngs:
        inputs += ["-loop", "1", "-t", f"{seg.dur:.2f}", "-i", str(p)]
    chain, last = [], "[0:v]"
    for k, (start, end, _, _) in enumerate(seg.captions):
        tag = f"[v{k}]"
        chain.append(f"{last}[{k + 2}:v]overlay=0:0:enable='between(t,{start:.2f},{end:.2f})'{tag}")
        last = tag
    ms = int(LEAD * 1000)
    chain.append(f"[1:a]adelay={ms}|{ms},apad[a]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(chain), "-map", last, "-map", "[a]",
         "-t", f"{seg.dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)])


def srt_time(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def write_srt(segs: list[Seg], lang: str, out: Path):
    lines, n, offset = [], 1, 0.0
    for seg in segs:
        for start, end, en, idt in seg.captions:
            lines += [str(n), f"{srt_time(offset + start)} --> {srt_time(offset + end)}", en if lang == "en" else idt, ""]
            n += 1
        offset += seg.dur
    out.write_text("\n".join(lines), encoding="utf-8")


def finalize(parts: list[Path], out: Path):
    lst = out.with_suffix(".txt")
    lst.write_text("\n".join(f"file '{p}'" for p in parts))
    joined = out.with_name(out.stem + "_joined.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    total = duration(joined)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(joined),
         "-vf", f"fade=t=in:st=0:d=0.4,fade=t=out:st={total - 0.7:.2f}:d=0.7",
         "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,afade=t=out:st={total - 0.7:.2f}:d=0.7",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)])
    joined.unlink()
    lst.unlink()


async def build(kind: str, spec: list[dict]):
    print(f"\n== {kind}")
    segs = build_narration(kind, spec)
    work = BUILD / kind
    bot_reply = bot_reply_text()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        parts = []
        for seg in segs:
            clip = await record_segment(browser, seg, kind, bot_reply)
            pngs = []
            for k, (_, _, en, _) in enumerate(seg.captions):
                p = work / f"cap_{seg.idx:02d}_{k}.png"
                await render_png(browser, cards.subtitle_html(en), p)
                pngs.append(p)
            part = work / f"seg_{seg.idx:02d}.mp4"
            compose_segment(seg, clip, pngs, part)
            parts.append(part)
        await render_png(browser, cards.thumbnail_html(kind), OUT / f"neraca-fakta-{kind}-thumbnail.png",
                         size=(1280, 720), transparent=False)
        await browser.close()
    OUT.mkdir(exist_ok=True)
    final = OUT / f"neraca-fakta-{kind}.mp4"
    finalize(parts, final)
    write_srt(segs, "id", OUT / f"neraca-fakta-{kind}.id.srt")
    write_srt(segs, "en", OUT / f"neraca-fakta-{kind}.en.srt")
    print(f"  -> {final.relative_to(ROOT)}  {duration(final):.1f}s")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    BUILD.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    jobs = {"teaser": TEASER, "judging": JUDGING}
    for kind, spec in jobs.items():
        if which in (kind, "all"):
            asyncio.run(build(kind, spec))


if __name__ == "__main__":
    main()
