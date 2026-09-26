import { createContext, useContext } from "react";
import type { ClaimType, Lang, Text, VerdictLabel } from "./types";

// Every UI string, in both languages. Backend text (reasons, notes) arrives as {id, en}.
const STRINGS = {
  appName: { id: "Neraca Fakta", en: "Fact Ledger" },
  docTitle: { id: "Neraca Fakta · Verifikasi klaim saham", en: "Fact Ledger · Stock claim verification" },
  slogan: { id: "Untuk investor ritel Indonesia", en: "For Indonesian retail investors" },
  heroTitle: {
    id: "Setiap klaim saham, diverifikasi dengan data resmi.",
    en: "Every stock claim, verified against official data.",
  },
  heroSub: {
    id: "Tempel pesan, tautan artikel atau video, maupun tangkapan layar media sosial. Setiap klaim angka dicocokkan dengan laporan keuangan resmi emiten di Bursa Efek Indonesia.",
    en: "Paste a message, an article or video link, or a social media screenshot. Every numeric claim is matched against the company's official financial reports on the Indonesia Stock Exchange.",
  },
  step1: { id: "Kirim kontennya", en: "Share the content" },
  step1Sub: { id: "Pesan, tautan, video, atau tangkapan layar", en: "Message, link, video or screenshot" },
  step2: { id: "Klaim dipilah", en: "Claims extracted" },
  step2Sub: { id: "Laba, pendapatan, dividen, market cap", en: "Profit, revenue, dividends, market cap" },
  step3: { id: "Dicek ke data", en: "Checked against data" },
  step3Sub: { id: "Putusan dihitung, bukan ditebak", en: "Verdicts are computed, not guessed" },
  inputLabel: { id: "Pesan atau tautan yang ingin dicek", en: "Message or link to check" },
  placeholder: {
    id: "Contoh: $TLKM laba naik 20% YoY, dividen yield 9%. Target 4000 bulan depan! Atau tempel tautan https://…",
    en: "E.g. $TLKM laba naik 20% YoY, dividen yield 9%. Target 4000 bulan depan! Or paste a link https://…",
  },
  tryExample: { id: "Coba contoh", en: "Try an example" },
  exHype: { id: "Pesan hype", en: "Hype message" },
  exDividend: { id: "Saham dividen", en: "Dividend stock" },
  exWrong: { id: "Klaim keliru", en: "Wrong claims" },
  check: { id: "Cek fakta", en: "Fact-check" },
  checking: { id: "Memeriksa…", en: "Checking…" },
  shortcut: { id: "⌘/Ctrl + Enter", en: "⌘/Ctrl + Enter" },
  chars: { id: "{n} / 4000 karakter", en: "{n} / 4000 characters" },
  genericError: { id: "Terjadi kesalahan.", en: "Something went wrong." },
  apiOffline: { id: "API tidak terhubung", en: "API not connected" },
  liveData: { id: "Data live", en: "Live data" },
  offlineData: { id: "Mode offline", en: "Offline mode" },
  credits: { id: "Kredit: {spent} / {cap}", en: "Credits: {spent} / {cap}" },
  offlineTickers: { id: "Data offline: {list}", en: "Offline data: {list}" },
  themeSystem: { id: "Tema: ikuti sistem", en: "Theme: follow system" },
  themeLight: { id: "Tema: terang", en: "Theme: light" },
  themeDark: { id: "Tema: gelap", en: "Theme: dark" },
  language: { id: "Bahasa", en: "Language" },

  // Results
  scoreLabel: { id: "Skor kesesuaian", en: "Accuracy score" },
  scoreHelp: {
    id: "Porsi klaim yang bisa dicek dan sesuai data (sebagian sesuai dihitung setengah).",
    en: "Share of checkable claims that match the data (partial matches count half).",
  },
  claimsChecked: { id: "{n} klaim diperiksa", en: "{n} claims checked" },
  oneClaimChecked: { id: "1 klaim diperiksa", en: "1 claim checked" },
  noClaims: { id: "Tidak ada klaim ditemukan", en: "No claims found" },
  headlineGood: { id: "Sebagian besar sesuai data", en: "Mostly matches the data" },
  headlineMixed: { id: "Campuran: cek detailnya", en: "Mixed: read the details" },
  headlineBad: { id: "Banyak klaim tidak sesuai data", en: "Many claims don't match the data" },
  headlineNone: { id: "Tidak ada yang bisa diverifikasi", en: "Nothing could be verified" },
  filterAll: { id: "Semua", en: "All" },
  filterHint: { id: "Klik untuk menyaring", en: "Click to filter" },
  copySummary: { id: "Salin ringkasan", en: "Copy summary" },
  copied: { id: "Tersalin!", en: "Copied!" },
  originalMessage: { id: "Pesan asli", en: "Original message" },
  originalHint: { id: "Arahkan kursor ke bagian yang disorot untuk melihat putusannya.", en: "Hover a highlight to see its verdict." },
  claimsTitle: { id: "Putusan per klaim", en: "Verdict per claim" },
  claim: { id: "Klaim", en: "Claimed" },
  data: { id: "Data", en: "Data" },
  okZone: { id: "Zona sesuai", en: "Match zone" },
  partialZone: { id: "Zona sebagian", en: "Partial zone" },
  howComputed: { id: "Cara menghitung", en: "How it's computed" },
  tolGrowth: {
    id: "Sesuai jika selisih ≤ maks(2 poin, 10% dari data). Sebagian jika arahnya sama dan selisih ≤ maks(5 poin, 50%).",
    en: "Match if within max(2 pts, 10% of actual). Partial if same direction and within max(5 pts, 50%).",
  },
  tolYield: {
    id: "Sesuai jika selisih ≤ 0,5 poin persen. Sebagian jika ≤ 1,5 poin.",
    en: "Match if within 0.5 percentage points. Partial if within 1.5 points.",
  },
  tolAmount: {
    id: "Sesuai jika selisih ≤ 5%. Sebagian jika ≤ {p}%.",
    en: "Match if within 5%. Partial if within {p}%.",
  },
  tolUnverifiable: {
    id: "Prediksi harga, janji, dan rumor tidak tercatat di laporan keuangan, jadi tidak dinilai.",
    en: "Price predictions, promises and rumours aren't in financial reports, so they aren't graded.",
  },
  period: { id: "Periode", en: "Period" },
  showNoData: { id: "Tidak ada klaim dengan status ini.", en: "No claims with this status." },

  // Company
  companyTitle: { id: "Data emiten", en: "Company data" },
  marketCap: { id: "Kapitalisasi pasar", en: "Market cap" },
  rank: { id: "Peringkat #{n} di IDX", en: "Rank #{n} on IDX" },
  yoyRevenue: { id: "Pendapatan YoY", en: "Revenue YoY" },
  yoyEarnings: { id: "Laba YoY", en: "Earnings YoY" },
  dividendYield: { id: "Dividend yield", en: "Dividend yield" },
  ttm: { id: "12 bulan terakhir", en: "trailing 12 months" },
  eps: { id: "EPS", en: "EPS" },
  latestQuarter: { id: "{q} vs tahun lalu", en: "{q} vs a year earlier" },
  noDividend: { id: "Tidak ada", en: "None" },
  tabPrice: { id: "Harga 90 hari", en: "90-day price" },
  tabFinancials: { id: "Kinerja tahunan", en: "Annual results" },
  tabDividends: { id: "Riwayat dividen", en: "Dividend history" },
  showTable: { id: "Tabel", en: "Table" },
  showChart: { id: "Grafik", en: "Chart" },
  revenue: { id: "Pendapatan", en: "Revenue" },
  earnings: { id: "Laba bersih", en: "Net income" },
  close: { id: "Harga penutupan", en: "Closing price" },
  dateCol: { id: "Tanggal", en: "Date" },
  yearCol: { id: "Tahun", en: "Year" },
  yieldCol: { id: "Yield", en: "Yield" },
  dpsCol: { id: "Dividen/saham", en: "Dividend/share" },
  range52: { id: "Rentang 52 minggu", en: "52-week range" },
  low: { id: "Terendah", en: "Low" },
  high: { id: "Tertinggi", en: "High" },
  ath: { id: "Tertinggi sepanjang masa {p} ({d})", en: "All-time high {p} ({d})" },
  noPrices: { id: "Data harga harian tidak tersedia.", en: "Daily price data isn't available." },
  noFinancials: { id: "Data keuangan tahunan tidak tersedia.", en: "Annual financial data isn't available." },
  noDividends: { id: "Emiten ini belum membagikan dividen dalam data.", en: "This company has no dividends in the data." },
  priceChartTitle: { id: "Harga penutupan harian, {from} – {to}", en: "Daily close, {from} – {to}" },
  finChartTitle: { id: "Pendapatan dan laba bersih per tahun (IDR)", en: "Revenue and net income per year (IDR)" },
  divChartTitle: { id: "Dividend yield per tahun", en: "Dividend yield per year" },
  change: { id: "{v} hari ini", en: "{v} today" },

  meta: { id: "Ekstraksi: {x} · Data: {d} · Kredit terpakai: {c}", en: "Extraction: {x} · Data: {d} · Credits used: {c}" },
  rulesName: { id: "berbasis aturan", en: "rule-based" },
  sourceLive: { id: "Sectors API (live)", en: "Sectors API (live)" },
  sourceOffline: { id: "offline", en: "offline" },
  footer: {
    id: "Alat informasi, bukan saran investasi. Data keuangan dari Sectors. Klaim prediksi harga tidak bisa diverifikasi dan tidak kami nilai.",
    en: "An information tool, not investment advice. Financial data from Sectors. Price predictions can't be verified and aren't graded.",
  },
  summaryDisclaimer: { id: "Bukan saran investasi.", en: "Not investment advice." },

  chatVia: { id: "Atau cek langsung dari chat:", en: "Or check straight from chat:" },
  viaTelegram: { id: "Telegram", en: "Telegram" },
  viaWhatsApp: { id: "WhatsApp", en: "WhatsApp" },

  demoNotice: {
    id: "Versi demo: data tersimpan untuk {list}. Tidak memakai kredit API.",
    en: "Demo version: saved data for {list}. Uses no API credits.",
  },

  // Links & screenshots
  sourcesHint: {
    id: "Bisa juga tempel tautan artikel, blog, YouTube, TikTok, Threads, Instagram, Facebook, atau X, dan lampirkan tangkapan layar.",
    en: "You can also paste links to articles, blogs, YouTube, TikTok, Threads, Instagram, Facebook or X, and attach screenshots.",
  },
  attach: { id: "Lampirkan tangkapan layar", en: "Attach screenshots" },
  attachHint: { id: "Maks. 3 gambar, 5 MB. Bisa juga tempel (Ctrl/⌘+V) atau seret ke sini.", en: "Up to 3 images, 5 MB each. You can also paste (Ctrl/⌘+V) or drag them here." },
  attachNeedsAI: { id: "Membaca gambar butuh penyedia AI (⚙ AI).", en: "Reading images needs an AI provider (⚙ AI)." },
  attachTooMany: { id: "Maksimal 3 gambar.", en: "At most 3 images." },
  attachBadType: { id: "Hanya gambar PNG, JPEG, WebP, atau GIF hingga 5 MB.", en: "Only PNG, JPEG, WebP or GIF images up to 5 MB." },
  removeImage: { id: "Hapus gambar", en: "Remove image" },
  dropHere: { id: "Lepaskan gambar di sini", en: "Drop images here" },
  sourcesTitle: { id: "Sumber yang dibaca", en: "Sources read" },
  srcOk: { id: "Dibaca", en: "Read" },
  srcPartial: { id: "Sebagian", en: "Partial" },
  srcBlocked: { id: "Terkunci", en: "Locked" },
  srcError: { id: "Gagal", en: "Failed" },
  srcChars: { id: "{n} karakter", en: "{n} characters" },
  videoAnalyzed: { id: "Video dianalisis oleh Gemini", en: "Video analysed by Gemini" },
  mediaText: { id: "Teks dari gambar/video", en: "Text from images/video" },

  // Market panels
  latest: { id: "Terkini", en: "Latest" },
  newsTickerLabel: { id: "Berita pasar terkini", en: "Latest market news" },
  markets: { id: "Pasar", en: "Markets" },
  ihsgName: { id: "IHSG · Indeks Harga Saham Gabungan", en: "IHSG · Jakarta Composite Index" },
  indicesTitle: { id: "Indeks utama", en: "Key indices" },
  idxMarketCap: { id: "Kapitalisasi pasar IDX", en: "IDX market cap" },
  commoditiesTitle: { id: "Komoditas", en: "Commodities" },
  forexTitle: { id: "Kurs Rupiah", en: "Rupiah exchange rates" },
  forexSource: { id: "Kurs referensi ECB via Frankfurter · {d}", en: "ECB reference rates via Frankfurter · {d}" },
  sectorsSource: { id: "Data: Sectors · per {d}", en: "Data: Sectors · as of {d}" },
  moversTitle: { id: "Penggerak pasar", en: "Top movers" },
  gainers: { id: "Naik", en: "Gainers" },
  losers: { id: "Turun", en: "Losers" },
  mostTraded: { id: "Paling aktif", en: "Most traded" },
  shares: { id: "lembar", en: "shares" },
  newsTitle: { id: "Berita emiten", en: "Company news" },
  newsNote: {
    id: "Ringkasan judul oleh Sectors (bahasa Inggris). Klik untuk membaca artikel asli.",
    en: "Headline summaries by Sectors. Click to read the original article.",
  },
  unavailOffline: { id: "Belum ada data offline untuk bagian ini.", en: "No offline data for this section yet." },
  unavailBudget: { id: "Dijeda untuk menghemat kredit API.", en: "Paused to save API credits." },
  unavailError: { id: "Gagal memuat data.", en: "Couldn't load this data." },
  panelsOff: { id: "Panel pasar dinonaktifkan di server.", en: "Market panels are turned off on this server." },
  offlineSnapshot: { id: "Cuplikan offline", en: "Offline snapshot" },
  perUnit: { id: "per 1 {c}", en: "per 1 {c}" },

  // Panel customization
  highlights: { id: "Sorotan", en: "Highlights" },
  secIhsg: { id: "IHSG", en: "IHSG (Composite)" },
  customizePanels: { id: "Atur panel", en: "Customize panels" },
  customizeIntro: {
    id: "Pilih data yang tampil di panel samping. Perubahan langsung diterapkan dan disimpan di browser ini.",
    en: "Choose what the side panels show. Changes apply right away and are saved in this browser.",
  },
  sectionsTitle: { id: "Bagian & tata letak", en: "Sections & layout" },
  sideLeft: { id: "Panel kiri", en: "Left panel" },
  sideRight: { id: "Panel kanan", en: "Right panel" },
  sideEmpty: { id: "Tidak ada bagian di panel ini.", en: "No sections in this panel." },
  moveUp: { id: "Naikkan", en: "Move up" },
  moveDown: { id: "Turunkan", en: "Move down" },
  toRight: { id: "Ke kanan →", en: "To right →" },
  toLeft: { id: "← Ke kiri", en: "← To left" },
  showTicker: { id: "Tampilkan baris berita terkini di atas", en: "Show the latest-news ticker at the top" },
  watchlistTitle: { id: "Daftar pantau", en: "Watchlist" },
  watchlistEmpty: { id: "Pantau hingga 5 saham pilihan Anda di sini.", en: "Track up to 5 stocks of your choice here." },
  watchlistAdd: { id: "Tambah saham", en: "Add stocks" },
  watchlistHelp: {
    id: "Maks. {n} kode saham IDX. Tiap saham baru memakai 1 kredit API (disimpan 6 jam).",
    en: "Up to {n} IDX codes. Each new stock uses 1 API credit (cached for 6 hours).",
  },
  watchInvalid: { id: "Masukkan kode saham 4 huruf, mis. BBCA.", en: "Enter a 4-letter stock code, e.g. BBCA." },
  watchFull: { id: "Daftar pantau penuh (maks. {n}).", en: "Watchlist is full (max {n})." },
  watchNotFound: { id: "Kode tidak ditemukan", en: "Code not found" },
  watchOffline: { id: "Tidak ada di data offline", en: "Not in offline data" },
  nothingSelected: { id: "Belum ada yang dipilih. Atur lewat ⚙.", en: "Nothing selected. Choose items via ⚙." },
  add: { id: "Tambah", en: "Add" },
  removeX: { id: "Hapus {x}", en: "Remove {x}" },
  newsCount: { id: "Jumlah berita", en: "Number of news items" },
  resetLayout: { id: "Kembalikan default", en: "Reset to default" },
  done: { id: "Selesai", en: "Done" },

  // Settings dialog
  aiSettings: { id: "Pengaturan AI", en: "AI settings" },
  aiIntro: {
    id: "AI membaca pesan dan memilah klaimnya. Putusan tetap dihitung dari data, bukan oleh AI.",
    en: "AI reads the message and extracts its claims. Verdicts are still computed from data, not by the AI.",
  },
  provider: { id: "Penyedia", en: "Provider" },
  serverDefault: { id: "Default server", en: "Server default" },
  currently: { id: "Saat ini: {p}", en: "Currently: {p}" },
  serverKey: { id: "Kunci server tersedia", en: "Server key available" },
  needsKey: { id: "Perlu kunci Anda", en: "Needs your key" },
  noAI: { id: "Tanpa AI", en: "No AI" },
  noAISub: { id: "Ekstraktor berbasis aturan, gratis", en: "Rule-based extractor, free" },
  apiKeyFor: { id: "Kunci API {p}", en: "{p} API key" },
  keyServerOnly: { id: "Server ini hanya memakai kuncinya sendiri", en: "This server only uses its own keys" },
  keyUseServer: { id: "Kosongkan untuk memakai kunci server", en: "Leave empty to use the server key" },
  keyPaste: { id: "Tempel kunci {p} ({x}…)", en: "Paste your {p} key ({x}…)" },
  show: { id: "Tampilkan", en: "Show" },
  hide: { id: "Sembunyikan", en: "Hide" },
  prefixWarn: {
    id: "Kunci {p} biasanya diawali “{x}”. Pastikan penyedianya benar.",
    en: "{p} keys usually start with “{x}”. Make sure the provider is right.",
  },
  model: { id: "Model", en: "Model" },
  optional: { id: "(opsional)", en: "(optional)" },
  remember: { id: "Ingat di perangkat ini", en: "Remember on this device" },
  keyPrivacy: {
    id: "Kunci disimpan hanya di browser ini ({when}) dan dikirim ke server ini hanya saat pengecekan. Server tidak menyimpannya.",
    en: "Keys are stored only in this browser ({when}) and sent to this server only when checking. The server doesn't store them.",
  },
  untilCleared: { id: "sampai dihapus", en: "until cleared" },
  untilTabClosed: { id: "sampai tab ditutup", en: "until the tab closes" },
  testOk: { id: "Berhasil: {p} ({m}) merespons.", en: "Success: {p} ({m}) responded." },
  testRules: { id: "Siap: ekstraktor berbasis aturan.", en: "Ready: rule-based extractor." },
  testFail: { id: "Gagal menguji.", en: "Test failed." },
  clearKeys: { id: "Hapus semua kunci", en: "Clear all keys" },
  testConn: { id: "Uji koneksi", en: "Test connection" },
  testing: { id: "Menguji…", en: "Testing…" },
  save: { id: "Simpan", en: "Save" },
  closeLabel: { id: "Tutup", en: "Close" },
} satisfies Record<string, Text>;

export type StringKey = keyof typeof STRINGS;

const VERDICT: Record<VerdictLabel, Text> = {
  "Sesuai data": { id: "Sesuai data", en: "Matches data" },
  "Sebagian sesuai": { id: "Sebagian sesuai", en: "Partly matches" },
  "Tidak sesuai": { id: "Tidak sesuai", en: "Doesn't match" },
  "Tidak dapat diverifikasi": { id: "Tidak dapat diverifikasi", en: "Can't be verified" },
};

const CLAIM_TYPE: Record<ClaimType, Text> = {
  revenue_growth: { id: "Pertumbuhan pendapatan", en: "Revenue growth" },
  profit_growth: { id: "Pertumbuhan laba", en: "Profit growth" },
  net_income: { id: "Laba bersih", en: "Net income" },
  dividend_yield: { id: "Dividend yield", en: "Dividend yield" },
  market_cap: { id: "Kapitalisasi pasar", en: "Market cap" },
  unverifiable: { id: "Tidak dapat dicek", en: "Not checkable" },
};

export interface I18n {
  lang: Lang;
  t: (key: StringKey, params?: Record<string, string | number>) => string;
  tx: (text: Text | null | undefined) => string;
  verdict: (label: VerdictLabel) => string;
  claimType: (type: ClaimType) => string;
}

export function makeI18n(lang: Lang): I18n {
  return {
    lang,
    t: (key, params) =>
      STRINGS[key][lang].replace(/\{(\w+)\}/g, (_, k) => (params && k in params ? String(params[k]) : `{${k}}`)),
    tx: (text) => (text ? text[lang] : ""),
    verdict: (label) => VERDICT[label][lang],
    claimType: (type) => CLAIM_TYPE[type][lang],
  };
}

export const I18nContext = createContext<I18n>(makeI18n("id"));
export const useI18n = () => useContext(I18nContext);
