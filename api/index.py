"""Vercel serverless entry point: the FastAPI app, in demo mode.

The public deployment runs on the offline snapshots in fixtures/raw/ (bundled at deploy time
from the deployer's machine, never committed), so it can never spend Sectors credits.
Serverless disks are read-only except /tmp, which also holds the per-instance cache.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["DATA_SOURCE"] = "fixtures"  # forced: a public URL must not spend credits
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("CACHE_PATH", "/tmp/cekfakta-cache.sqlite")

from cekfakta.api import app  # noqa: E402,F401
