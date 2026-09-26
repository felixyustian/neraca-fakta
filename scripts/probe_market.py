"""Fetch live market-panel data once and save it for offline mode.

Usage:
    python scripts/probe_market.py --dry-run   # planned Sectors calls and credit cost, spends nothing
    python scripts/probe_market.py             # real calls; writes fixtures/raw/market/*.json

About 12 credits on an empty cache (0 for anything already cached). Forex comes from the
free ECB/Frankfurter API and costs nothing.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cekfakta.config import load_settings  # noqa: E402
from cekfakta.market import MarketService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    settings = replace(load_settings(), data_source="live")
    if not settings.sectors_api_key:
        print("SECTORS_API_KEY is not set.")
        return 1
    svc = MarketService(settings, record=not args.dry_run, dry_run=args.dry_run)
    before = svc.client.credits_spent
    snap = svc.snapshot()

    if args.dry_run:
        total = sum(c.est_credits for c in svc.client.planned)
        print(f"DRY RUN: {len(svc.client.planned)} uncached Sectors calls, ~{total} credits"
              " (later calls depend on earlier results, so this is a lower bound)")
        for c in svc.client.planned:
            print(f"  {c.est_credits:>2} cr  {c.path}  {c.params}")
        return 0

    print(f"IHSG: {snap.ihsg}")
    print(f"indices: {[(q.code, round(q.value, 2), q.change_pct and round(q.change_pct, 2)) for q in snap.indices]}")
    print(f"gainers: {[(m.symbol, round(m.change_pct, 2)) for m in snap.gainers]}")
    print(f"losers: {[(m.symbol, round(m.change_pct, 2)) for m in snap.losers]}")
    print(f"most traded ({snap.most_traded_date}): {[m.symbol for m in snap.most_traded]}")
    print(f"commodities: {[(c.name, c.price, c.date) for c in snap.commodities]}")
    print(f"forex: {[(f.currency, round(f.rate, 2), f.date) for f in snap.forex]}")
    print(f"news: {len(snap.news)} items, newest {snap.news[0].timestamp if snap.news else '-'}")
    print(f"unavailable: {snap.unavailable}")
    print(f"\nCredits spent: {svc.client.credits_spent - before} | ledger total {svc.client.credits_spent}"
          f" | cap {settings.credit_hard_cap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
