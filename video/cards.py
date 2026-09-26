"""HTML for the title cards, subtitles and thumbnails. Rendered by headless Chromium.

Cards use the app's dark palette and animate with CSS, so they are recorded like any page.
"""
from __future__ import annotations

import html

BASE_CSS = """
:root { --bg:#0c1110; --surface:#151c1a; --surface2:#1b2321; --text:#e8eeec; --text2:#b7c2be;
  --muted:#8a9692; --border:#26302d; --accent:#2dd4bf; --accent2:#5eead4; --ok:#0ca30c; --okb:#0a7a0a;
  --partial:#fab219; --bad:#d03b3b; --unk:#66655f; --s1:#3987e5; }
* { box-sizing:border-box; margin:0; }
html, body { width:1920px; height:1080px; overflow:hidden; background:var(--bg); color:var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; -webkit-font-smoothing:antialiased; }
body { background: radial-gradient(1400px 700px at 10% -10%, rgb(45 212 191 / .14), transparent 60%),
  radial-gradient(1100px 600px at 100% 110%, rgb(57 135 229 / .12), transparent 60%), var(--bg); }
.wrap { position:absolute; inset:0; padding:120px 160px 200px; display:flex; flex-direction:column; justify-content:center; }
.brand { position:absolute; top:64px; left:160px; display:flex; align-items:center; gap:16px; font-weight:800;
  font-size:30px; letter-spacing:-.02em; opacity:0; animation: fade .6s .1s forwards; }
.logo { width:52px; height:52px; border-radius:15px; display:grid; place-items:center; color:#04201c;
  background:linear-gradient(135deg, var(--accent), var(--accent2)); }
.logo.big { width:120px; height:120px; border-radius:34px; }
.eyebrow { font-size:26px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); }
h1 { font-size:84px; line-height:1.06; letter-spacing:-.035em; font-weight:800; }
h2 { font-size:60px; line-height:1.1; letter-spacing:-.03em; font-weight:800; }
.sub { font-size:34px; color:var(--text2); line-height:1.35; }
.en { font-size:26px; color:var(--muted); margin-top:10px; }
.up { opacity:0; transform:translateY(24px); animation: up .7s cubic-bezier(.2,.8,.2,1) forwards; }
@keyframes up { to { opacity:1; transform:none; } }
@keyframes fade { to { opacity:1; } }
@keyframes pop { 0% { opacity:0; transform:scale(.6); } 70% { transform:scale(1.08); } 100% { opacity:1; transform:none; } }
.chips { display:flex; gap:14px; flex-wrap:wrap; }
.chip { font-size:28px; font-weight:700; padding:12px 22px; border-radius:999px; background:var(--surface2);
  border:1px solid var(--border); }
"""


def _page(body: str, extra_css: str = "") -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}{extra_css}</style></head><body>{body}</body></html>"


LOGO_SVG = ("<svg viewBox='0 0 24 24' width='{s}' height='{s}'><path d='M5 12.5l4.2 4.2L19 7' fill='none' "
            "stroke='currentColor' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/></svg>")


def brand() -> str:
    return f"<div class='brand'><span class='logo'>{LOGO_SVG.format(s=28)}</span>Neraca Fakta</div>"


def delays(n: int, start: float, step: float) -> list[str]:
    return [f"animation-delay:{start + i * step:.2f}s" for i in range(n)]


def card_hook(dur: float) -> str:
    bubbles = [
        "🔥 INFO A1 🔥 $GOTO laba naik 200%!",
        "TLKM dividen yield 12%, wajib koleksi!",
        "Target 100 minggu depan, pasti ARA 🚀",
    ]
    d = delays(3, 0.5, 0.9)
    items = "".join(
        f"<div class='bubble up' style='{d[i]}'><span class='fwd'>↪ Diteruskan</span>{html.escape(b)}"
        f"<span class='time'>09:{41 + i:02d}</span></div>" for i, b in enumerate(bubbles))
    q_delay = 0.5 + 3 * 0.9 + 0.3
    css = """
    .chat { display:flex; flex-direction:column; gap:22px; align-items:flex-start; }
    .bubble { position:relative; font-size:40px; font-weight:600; background:#1f2a27; border:1px solid var(--border);
      padding:22px 30px 34px; border-radius:6px 26px 26px 26px; max-width:1100px; }
    .fwd { display:block; font-size:22px; color:var(--muted); font-weight:600; margin-bottom:6px; font-style:italic; }
    .time { position:absolute; right:18px; bottom:8px; font-size:20px; color:var(--muted); }
    .q { position:absolute; right:160px; top:50%; transform:translateY(-50%); text-align:right; }
    .q h1 { font-size:150px; color:var(--accent); opacity:0; animation: pop .6s forwards; }
    .label { position:absolute; left:160px; bottom:130px; font-size:22px; color:var(--muted); }
    """
    body = (f"{brand()}<div class='wrap'><div class='chat'>{items}</div></div>"
            f"<div class='q'><h1 style='animation-delay:{q_delay:.2f}s'>Benarkah?</h1>"
            f"<div class='en up' style='animation-delay:{q_delay + .3:.2f}s;font-size:34px'>True or not?</div></div>"
            f"<div class='label'>Contoh pesan · Sample messages</div>")
    return _page(body, css)


def card_problem(dur: float) -> str:
    chans = ["WhatsApp", "Telegram", "TikTok", "YouTube", "Instagram", "Facebook"]
    d = delays(len(chans), 1.4, 0.18)
    chips = "".join(f"<span class='chip up' style='{d[i]}'>{c}</span>" for i, c in enumerate(chans))
    css = """.big { font-size:170px; font-weight:800; letter-spacing:-.04em; color:var(--partial); line-height:1; }
    .row { display:flex; gap:80px; align-items:center; margin-top:56px; }"""
    body = (f"{brand()}<div class='wrap'>"
            f"<div class='eyebrow up'>Masalahnya · The problem</div>"
            f"<h1 class='up' style='animation-delay:.25s;margin-top:22px'>Tips saham menyebar cepat.<br>Angkanya jarang dicek.</h1>"
            f"<div class='en up' style='animation-delay:.45s'>Stock tips spread fast. Their numbers rarely get checked.</div>"
            f"<div class='chips' style='margin-top:48px'>{chips}</div>"
            f"<div class='row up' style='animation-delay:{1.4 + len(chans) * .18 + .4:.2f}s'>"
            f"<div class='big'>“+200%”</div><div class='sub'>laba naik dua ratus persen…<br><b style='color:var(--text)'>benarkah?</b></div></div>"
            f"</div>")
    return _page(body, css)


def card_steps(dur: float) -> str:
    steps = [
        ("1", "Kirim kontennya", "Share the content", "Pesan, tautan, video, atau tangkapan layar"),
        ("2", "Klaim dipilah", "Claims extracted", "Laba, pendapatan, dividen, market cap"),
        ("3", "Dicek ke data resmi", "Checked against official data", "Putusan dihitung, bukan ditebak"),
    ]
    d = delays(3, 0.7, 0.8)
    cols = "".join(
        f"<div class='step up' style='{d[i]}'><span class='n'>{n}</span><h3>{t}</h3><div class='en'>{e}</div>"
        f"<p>{s}</p></div>" for i, (n, t, e, s) in enumerate(steps))
    css = """.steps { display:grid; grid-template-columns:repeat(3,1fr); gap:32px; margin-top:60px; }
    .step { background:var(--surface); border:1px solid var(--border); border-radius:28px; padding:44px; }
    .n { display:inline-grid; place-items:center; width:64px; height:64px; border-radius:50%; font-size:32px; font-weight:800;
      background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#04201c; }
    .step h3 { font-size:44px; margin-top:26px; letter-spacing:-.02em; }
    .step p { font-size:28px; color:var(--text2); margin-top:18px; line-height:1.35; }"""
    body = (f"{brand()}<div class='wrap'><div class='eyebrow up'>Solusinya · The solution</div>"
            f"<h1 class='up' style='animation-delay:.2s;margin-top:22px'>Neraca Fakta</h1>"
            f"<div class='sub up' style='animation-delay:.35s;margin-top:10px'>Setiap klaim saham, diverifikasi dengan data resmi.</div>"
            f"<div class='steps'>{cols}</div></div>")
    return _page(body, css)


def card_bots(dur: float, reply: str) -> str:
    lines = "".join(f"<div class='ln up' style='animation-delay:{0.45 + i * 0.045:.2f}s'>{html.escape(l) or '&nbsp;'}</div>"
                    for i, l in enumerate(reply.splitlines()))
    css = """.grid { display:grid; grid-template-columns: 1fr 820px; gap:90px; align-items:center; }
    .phone { background:#0f1614; border:2px solid var(--border); border-radius:48px; padding:34px; max-height:800px; overflow:hidden;
      box-shadow: 0 40px 100px rgb(0 0 0 / .5); }
    .user { margin-left:auto; max-width:560px; background:#123a33; border-radius:24px 24px 6px 24px; padding:18px 24px;
      font-size:24px; margin-bottom:22px; }
    .bot { background:var(--surface2); border:1px solid var(--border); border-radius:24px 24px 24px 6px; padding:22px 26px; }
    .ln { font-size:21px; line-height:1.42; white-space:pre-wrap; color:var(--text); }
    .note { font-size:22px; color:var(--muted); margin-top:18px; }
    .cmd { font-family: ui-monospace, Menlo, monospace; font-size:28px; color:var(--accent2); margin-top:14px; }"""
    body = (f"{brand()}<div class='wrap'><div class='grid'><div>"
            f"<div class='eyebrow up'>Chat bot</div>"
            f"<h2 class='up' style='animation-delay:.2s;margin-top:20px'>Telegram &amp; WhatsApp</h2>"
            f"<div class='sub up' style='animation-delay:.35s;margin-top:20px'>Kirim atau teruskan tips, tautan, atau foto. Di grup: balas dengan</div>"
            f"<div class='cmd up' style='animation-delay:.5s'>/cek</div>"
            f"<div class='note up' style='animation-delay:.6s'>Contoh balasan bot dari data demo · Sample bot reply from the demo data</div></div>"
            f"<div class='phone up' style='animation-delay:.3s'><div class='user'>{html.escape(reply_user_msg())}</div>"
            f"<div class='bot'>{lines}</div></div></div></div>")
    return _page(body, css)


def reply_user_msg() -> str:
    return "🔥 $GOTO laba naik 200% YoY! TLKM dividen yield 12%"


def card_arch(dur: float) -> str:
    boxes = [
        ("Masukan", "Input", "Pesan · tautan · tangkapan layar · video"),
        ("AI memilah klaim", "AI extracts claims", "Claude · OpenAI · Gemini, atau aturan"),
        ("Sectors Financial API", "Official IDX data", "laporan · kuartalan · harga harian · indeks · movers · berita"),
        ("Verifikasi oleh kode", "Deterministic check", "toleransi tetap, AI tidak memutuskan"),
        ("Putusan", "Verdicts", "web · Telegram · WhatsApp"),
    ]
    d = delays(len(boxes), 0.6, 0.75)
    items = ""
    for i, (t, e, s) in enumerate(boxes):
        hl = " hl" if "Sectors" in t else ""
        items += f"<div class='box up{hl}' style='{d[i]}'><h3>{t}</h3><div class='en'>{e}</div><p>{s}</p></div>"
        if i < len(boxes) - 1:
            items += f"<div class='arrow up' style='animation-delay:{0.6 + i * .75 + .4:.2f}s'>→</div>"
    css = """.flow { display:flex; align-items:stretch; gap:14px; margin-top:64px; }
    .box { flex:1; background:var(--surface); border:1px solid var(--border); border-radius:24px; padding:30px 26px; }
    .box.hl { border-color:var(--accent); box-shadow: 0 0 0 2px var(--accent) inset, 0 20px 60px rgb(45 212 191 / .15); }
    .box h3 { font-size:32px; letter-spacing:-.01em; line-height:1.15; }
    .box p { font-size:22px; color:var(--text2); margin-top:14px; line-height:1.4; }
    .arrow { align-self:center; font-size:40px; color:var(--muted); }"""
    body = (f"{brand()}<div class='wrap'><div class='eyebrow up'>Cara kerja · How it works</div>"
            f"<h2 class='up' style='animation-delay:.2s;margin-top:20px'>AI memilah. Data memutuskan.</h2>"
            f"<div class='en up' style='animation-delay:.3s'>AI extracts. Data decides.</div>"
            f"<div class='flow'>{items}</div></div>")
    return _page(body, css)


def card_eng(dur: float) -> str:
    tiles = [
        ("Cache + buku kredit", "Cache + credit ledger", "Batas atas kredit, respons disimpan"),
        ("99", "automated tests", "Tes otomatis, semua jaringan di-mock"),
        ("2 bahasa", "Bilingual", "Indonesia &amp; English, terang &amp; gelap"),
        ("Live di Vercel", "Live on Vercel", "Demo 0 kredit · neraca-fakta.vercel.app"),
    ]
    d = delays(len(tiles), 0.5, 0.6)
    cells = "".join(f"<div class='tile up' style='{d[i]}'><div class='v'>{v}</div><div class='en'>{e}</div><p>{s}</p></div>"
                    for i, (v, e, s) in enumerate(tiles))
    css = """.tiles { display:grid; grid-template-columns:repeat(4,1fr); gap:28px; margin-top:64px; }
    .tile { background:var(--surface); border:1px solid var(--border); border-radius:26px; padding:40px 34px; }
    .v { font-size:48px; font-weight:800; letter-spacing:-.025em; color:var(--accent2); line-height:1.1; }
    .tile p { font-size:24px; color:var(--text2); margin-top:16px; line-height:1.4; }"""
    body = (f"{brand()}<div class='wrap'><div class='eyebrow up'>Rekayasa · Engineering</div>"
            f"<h2 class='up' style='animation-delay:.2s;margin-top:20px'>Hemat, teruji, siap dipakai.</h2>"
            f"<div class='en up' style='animation-delay:.3s'>Cost-controlled, tested, ready to use.</div>"
            f"<div class='tiles'>{cells}</div></div>")
    return _page(body, css)


def card_end(dur: float) -> str:
    css = """.center { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;
      text-align:center; padding-bottom:120px; }
    .center .logo.big { opacity:0; animation: pop .7s .1s forwards; margin-bottom:40px; }
    .url { margin-top:44px; font-size:40px; font-weight:800; color:var(--accent2); padding:18px 36px; border-radius:999px;
      background:rgb(45 212 191 / .1); border:1px solid rgb(45 212 191 / .35); }
    .meta { margin-top:30px; font-size:24px; color:var(--muted); }"""
    body = ("<div class='center'>"
            f"<span class='logo big'>{LOGO_SVG.format(s=64)}</span>"
            "<h1 class='up' style='animation-delay:.35s'>Neraca Fakta</h1>"
            "<div class='sub up' style='animation-delay:.5s;margin-top:14px'>Setiap klaim saham, diverifikasi dengan data resmi.</div>"
            "<div class='en up' style='animation-delay:.6s'>Fact Ledger · Every stock claim, verified against official data.</div>"
            "<div class='url up' style='animation-delay:.9s'>neraca-fakta.vercel.app</div>"
            "<div class='meta up' style='animation-delay:1.1s'>Data: Sectors Financial API · Sectors Hackathon 2026 · github.com/felixyustian/neraca-fakta</div>"
            "</div>")
    return _page(body, css)


def subtitle_html(text: str) -> str:
    """Transparent 1920x1080 page with one caption near the bottom."""
    css = """html, body { background: transparent !important; }
    .cap { position:absolute; left:50%; bottom:64px; transform:translateX(-50%); max-width:1500px; text-align:center;
      font-size:40px; line-height:1.3; font-weight:650; color:#fff; padding:14px 30px; border-radius:14px;
      background: rgb(8 12 11 / .78); letter-spacing:-.005em; text-wrap: balance; }"""
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}{css}</style></head>"
            f"<body style='background:transparent'><div class='cap'>{html.escape(text)}</div></body></html>")


def thumbnail_html(kind: str) -> str:
    title = "Cek fakta tips saham dalam hitungan detik" if kind == "teaser" else "Neraca Fakta: demo &amp; cara kerja"
    tag = "TEASER · 1 MENIT" if kind == "teaser" else "DEMO · SECTORS HACKATHON 2026"
    css = """html, body { width:1280px; height:720px; }
    .t { position:absolute; inset:0; padding:70px 80px; display:flex; flex-direction:column; justify-content:center; }
    .tag { font-size:24px; font-weight:800; letter-spacing:.14em; color:var(--accent); }
    .t h1 { font-size:74px; line-height:1.04; margin-top:18px; max-width:760px; }
    .cards { position:absolute; right:60px; top:50%; transform:translateY(-50%); display:flex; flex-direction:column; gap:16px; }
    .v { display:flex; align-items:center; gap:14px; background:var(--surface); border:1px solid var(--border); border-radius:18px;
      padding:16px 22px; font-size:26px; font-weight:700; width:390px; }
    .i { width:40px; height:40px; border-radius:50%; display:grid; place-items:center; font-weight:900; color:#fff; font-size:22px; }
    .b { position:absolute; left:80px; bottom:50px; display:flex; align-items:center; gap:14px; font-size:30px; font-weight:800; }"""
    rows = [("✓", "var(--okb)", "Sesuai data", "GOTO +217,8%"), ("≈", "var(--partial)", "Sebagian", "TLKM +21,6%"),
            ("✕", "var(--bad)", "Tidak sesuai", "Yield 9,26%"), ("?", "var(--unk)", "Tak terverifikasi", "“Pasti ARA”")]
    cards = "".join(f"<div class='v'><span class='i' style='background:{c};{'color:#3b2a00' if '≈' in i else ''}'>{i}</span>"
                    f"<span>{l}<br><span style='font-size:20px;color:var(--muted);font-weight:600'>{s}</span></span></div>"
                    for i, c, l, s in rows)
    body = (f"<div class='t'><div class='tag'>{tag}</div><h1>{title}</h1></div><div class='cards'>{cards}</div>"
            f"<div class='b'><span class='logo'>{LOGO_SVG.format(s=28)}</span>Neraca Fakta</div>")
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}{css}</style></head><body>{body}</body></html>"


CARDS = {
    "card_hook": card_hook,
    "card_problem": card_problem,
    "card_steps": card_steps,
    "card_arch": card_arch,
    "card_eng": card_eng,
    "card_end": card_end,
}
