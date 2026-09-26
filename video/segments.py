"""Scripts for the teaser (~60 s) and the judging video (<= 3 min).

Each segment: an Indonesian narration line (spoken by TTS), the English subtitle burned into
the video, and the scene shown while it plays. Numbers in the narration match what the demo
message actually produces in the app (verified against /api/check).
"""

# One message that produces every verdict type: 2 matches, 1 partial, 1 mismatch, 1 unverifiable.
DEMO_MESSAGE = ("🔥 INFO A1 🔥 $GOTO laba Q2 2026 naik 200% YoY! Pendapatan tumbuh 30%. "
                "TLKM laba naik 30%, dividen yield 12%. Target 100 minggu depan, pasti ARA!")
LINK_MESSAGE = ("Benar nggak? https://investor.id/market/455602/perubahan-nasib-goto "
                "https://www.instagram.com/p/C0vYf6YrQ5Z/")

TEASER = [
    dict(scene="card_hook",
         id="Pesan saham berantai beredar setiap hari. Angkanya meyakinkan. Tapi, benarkah?",
         en="Stock tips get forwarded every day. The numbers sound convincing. But are they true?"),
    dict(scene="app_type",
         id="Kenalkan Neraca Fakta. Tempel pesannya, tautannya, atau tangkapan layarnya.",
         en="Meet Neraca Fakta. Paste the message, the link, or a screenshot."),
    dict(scene="app_check",
         id="Setiap klaim angka langsung dicek ke laporan keuangan resmi emiten di Bursa Efek Indonesia.",
         en="Every numeric claim is checked against official company reports on the Indonesia Stock Exchange."),
    dict(scene="app_verdicts",
         id="Hasilnya jelas: sesuai data, sebagian sesuai, atau tidak sesuai, lengkap dengan angka pembandingnya.",
         en="Clear verdicts: matches, partly matches, or doesn't match, with the real numbers side by side."),
    dict(scene="app_highlight",
         id="Janji cuan dan target harga? Ditandai tidak dapat diverifikasi.",
         en="Promises of profit and price targets? Flagged as unverifiable."),
    dict(scene="app_company",
         id="Plus grafik harga, kinerja tahunan, dan riwayat dividen.",
         en="Plus price charts, annual results, and dividend history."),
    dict(scene="app_markets",
         id="Pantau pasar, berita, dan kurs rupiah dalam satu layar.",
         en="Track the market, the news, and the rupiah on one screen."),
    dict(scene="app_bilingual",
         id="Tersedia dalam dua bahasa, dengan mode terang dan gelap.",
         en="Available in two languages, in light and dark mode."),
    dict(scene="card_bots",
         id="Juga bisa lewat Telegram dan WhatsApp.",
         en="Also on Telegram and WhatsApp."),
    dict(scene="card_end",
         id="Neraca Fakta. Setiap klaim saham, diverifikasi dengan data resmi.",
         en="Neraca Fakta. Every stock claim, verified against official data."),
]

JUDGING = [
    dict(scene="card_problem",
         id=("Di Indonesia, tips saham menyebar lewat WhatsApp, Telegram, TikTok, dan YouTube. "
             "Banyak yang mengutip angka, seperti laba naik dua ratus persen, tanpa ada yang mengeceknya."),
         en=("In Indonesia, stock tips spread through WhatsApp, Telegram, TikTok and YouTube. "
             "Many quote numbers, like profit up two hundred percent, that nobody checks.")),
    dict(scene="card_steps",
         id=("Neraca Fakta memeriksanya dalam hitungan detik. Kirim kontennya, klaim dipilah, "
             "lalu dicek ke data resmi. Putusannya dihitung, bukan ditebak."),
         en=("Neraca Fakta checks them in seconds. Share the content, the claims are extracted, "
             "then checked against official data. Verdicts are computed, not guessed.")),
    dict(scene="app_type",
         id="Ini contoh pesan hype yang umum. Kita tempel ke Neraca Fakta.",
         en="Here's a typical hype message. We paste it into Neraca Fakta."),
    dict(scene="app_check",
         id=("Lalu tekan cek fakta. Lima klaim diperiksa, dengan skor kesesuaian enam puluh tiga "
             "dari seratus. Campuran, jadi perlu dibaca detailnya."),
         en=("Then press fact-check. Five claims are checked, with an accuracy score of 63 out of 100. "
             "Mixed, so the details matter.")),
    dict(scene="app_verdicts",
         id=("Laba dan pendapatan GoTo sesuai data. Klaim laba Telkom naik tiga puluh persen hanya "
             "sebagian sesuai, karena datanya dua puluh satu koma enam persen. Dividen yield dua belas "
             "persen tidak sesuai: datanya sembilan koma dua enam persen."),
         en=("GoTo's profit and revenue claims match the data. Telkom's profit up 30% only partly matches: "
             "the data says 21.6%. A 12% dividend yield doesn't match: the data says 9.26%.")),
    dict(scene="app_highlight",
         id=("Setiap kartu menaruh angka klaim dan angka data pada satu skala, dengan zona toleransi yang "
             "jelas. Target harga dan janji cuan ditandai tidak dapat diverifikasi."),
         en=("Each card puts the claimed and actual numbers on one scale, with clear tolerance zones. "
             "Price targets and promises are flagged as unverifiable.")),
    dict(scene="app_company",
         id=("Di bawahnya ada data emiten: harga sembilan puluh hari, rentang lima puluh dua minggu, "
             "pendapatan dan laba tahunan, serta riwayat dividen."),
         en=("Below that is the company data: 90-day prices, the 52-week range, annual revenue and "
             "net income, and dividend history.")),
    dict(scene="app_links",
         id=("Tips tidak hanya datang dari chat. Tempel tautan artikel, YouTube, atau TikTok, dan isinya "
             "dibaca lalu dicek. Untuk Instagram atau Facebook yang terkunci, cukup unggah tangkapan layarnya."),
         en=("Tips don't only come from chats. Paste a link to an article, YouTube or TikTok, and it's read "
             "and checked. For login-walled Instagram or Facebook posts, just upload a screenshot.")),
    dict(scene="app_markets_custom",
         id=("Di sisi layar ada panel pasar: indeks, komoditas, kurs rupiah, saham penggerak, dan berita. "
             "Setiap pengguna bisa mengatur isinya dan menyimpan daftar pantau."),
         en=("Around it are market panels: indices, commodities, rupiah rates, top movers and news. "
             "Each user can customize them and keep a watchlist.")),
    dict(scene="card_bots",
         id=("Neraca Fakta juga hadir sebagai bot Telegram dan WhatsApp. Di grup, cukup balas pesan "
             "dengan perintah cek."),
         en=("Neraca Fakta also works as a Telegram and WhatsApp bot. In groups, just reply to a tip "
             "with the check command.")),
    dict(scene="card_arch",
         id=("Di balik layar, kecerdasan buatan hanya memilah klaim. Datanya dari Sectors Financial A P I: "
             "laporan emiten, keuangan kuartalan, harga harian, indeks, penggerak pasar, dan berita. "
             "Putusannya dihitung oleh kode, dengan toleransi tetap."),
         en=("Behind the scenes, AI only extracts the claims. The data comes from the Sectors Financial API: "
             "company reports, quarterly financials, daily prices, indices, movers and news. "
             "Verdicts are computed by code, with fixed tolerances.")),
    dict(scene="card_eng",
         id=("Setiap panggilan disimpan di cache dan dicatat di buku kredit dengan batas atas, jadi biayanya "
             "terkendali. Aplikasinya dua bahasa, punya sembilan puluh sembilan tes otomatis, dan demonya "
             "berjalan di Vercel."),
         en=("Every call is cached and recorded in a credit ledger with a hard cap, so costs stay under "
             "control. The app is bilingual, has 99 automated tests, and the demo runs on Vercel.")),
    dict(scene="card_end",
         id=("Neraca Fakta membantu investor ritel memilah fakta dari hype, sebelum mengambil keputusan. "
             "Coba sekarang di neraca fakta titik vercel titik app."),
         en=("Neraca Fakta helps retail investors separate facts from hype before they decide. "
             "Try it now at neraca-fakta.vercel.app.")),
]
