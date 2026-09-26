"""Day-1 probe: fetch real Sectors data for a few tickers and check what we can verify.

Usage:
    python scripts/probe.py --dry-run            # show planned calls and credit cost, spend nothing
    python scripts/probe.py                      # default tickers BBCA TLKM GOTO
    python scripts/probe.py BBRI ANTM BUMI       # your own tickers

Outputs:
    fixtures/raw/<SYMBOL>_<endpoint>.json   raw responses (git-ignored: Sectors data, not ours)
    a coverage table and a credit summary on stdout
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cekfakta.sectors_client import SectorsClient, SectorsError, normalize_symbol  # noqa: E402

FIXTURES = ROOT / "fixtures" / "raw"
REPORT_SECTIONS = ["overview", "financials", "dividend"]  # 3 credits
N_QUARTERS = 2                                            # 2 credits (QoQ possible)
DAILY_WINDOW_DAYS = 89                                     # 1 credit (max 90-day window)

# Fields the verifier depends on: (label, source, path into the JSON).
REQUIRED_FIELDS = [
    ("market cap",              "report",    ["overview", "market_cap"]),
    ("last close price",        "report",    ["overview", "last_close_price"]),
    ("last close date",         "report",    ["overview", "latest_close_date"]),
    ("YoY quarterly revenue %", "report",    ["financials", "yoy_quarter_revenue_growth"]),
    ("YoY quarterly earnings %","report",    ["financials", "yoy_quarter_earnings_growth"]),
    ("dividend yield TTM",      "report",    ["dividend", "yield_ttm"]),
    ("dividend TTM (IDR/share)","report",    ["dividend", "dividend_ttm"]),
    ("latest quarter date",     "quarterly", [0, "date"]),
    ("latest quarter revenue",  "quarterly", [0, "revenue"]),
    ("latest quarter earnings", "quarterly", [0, "earnings"]),
    ("previous quarter earnings","quarterly",[1, "earnings"]),
    ("daily close (latest)",    "daily",     [-1, "close"]),
    ("daily volume (latest)",   "daily",     [-1, "volume"]),
]


def dig(obj, path):
    for p in path:
        if obj is None:
            return None
        if isinstance(p, int):
            if not isinstance(obj, list):
                return None
            try:
                obj = obj[p]
            except IndexError:
                return None
        else:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(p)
    return obj


def save(symbol: str, name: str, body) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{symbol}_{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="*", default=["BBCA", "TLKM", "GOTO"])
    ap.add_argument("--dry-run", action="store_true", help="plan calls and cost; spend nothing")
    args = ap.parse_args()

    symbols = [normalize_symbol(t) for t in args.tickers]
    client = SectorsClient(dry_run=args.dry_run)
    end = date.today()
    start = end - timedelta(days=DAILY_WINDOW_DAYS)

    spent_before = client.credits_spent
    results: dict[str, dict[str, object]] = {}

    for sym in symbols:
        results[sym] = {}
        calls = {
            "report": lambda: client.company_report(sym, REPORT_SECTIONS),
            "quarterly": lambda: client.quarterly_financials(sym, N_QUARTERS),
            "daily": lambda: client.daily(sym, start.isoformat(), end.isoformat()),
        }
        for name, call in calls.items():
            try:
                body = call()
            except SectorsError as e:
                print(f"  ! {sym} {name}: HTTP {e.status} {e.body}")
                body = None
            results[sym][name] = body
            if body is not None:
                save(sym, name, body)

    if args.dry_run:
        total = sum(c.est_credits for c in client.planned)
        print(f"DRY RUN: {len(client.planned)} uncached calls, ~{total} credits")
        for c in client.planned:
            print(f"  {c.est_credits:>2} cr  {c.path}  {c.params}")
        print(f"Ledger so far: {client.credits_spent} spent, cap {client.settings.credit_hard_cap}")
        return 0

    # Coverage table: which verifier inputs actually exist in the real data.
    print("\nFIELD COVERAGE (value shown if present)")
    header = f"{'field':<28}" + "".join(f"{s:>22}" for s in symbols)
    print(header)
    print("-" * len(header))
    missing = 0
    for label, source, path in REQUIRED_FIELDS:
        row = f"{label:<28}"
        for sym in symbols:
            val = dig(results[sym].get(source), path)
            if val is None:
                missing += 1
                row += f"{'MISSING':>22}"
            else:
                row += f"{str(val)[:20]:>22}"
        print(row)

    spent = client.credits_spent - spent_before
    print(f"\nCredits spent this run: {spent}  |  ledger total: {client.credits_spent}"
          f"  |  cap: {client.settings.credit_hard_cap}")
    for path, calls, credits in client.store.spend_by_path():
        print(f"  {credits:>4} cr  {calls:>3} calls  {path}")
    per_ticker = spent / len(symbols) if symbols else 0
    print(f"\nCost per full check: ~{per_ticker:.1f} credits per new ticker")
    print(f"Missing fields: {missing}. Raw JSON saved to {FIXTURES.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
