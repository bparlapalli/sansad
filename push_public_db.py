"""
push_public_db.py — Send the trimmed public.db to the live site.

Reads the target URL and token from .env (or the environment):
    LIVE_SITE_URL=https://your-app.onrender.com
    INGEST_TOKEN=<same value set on the Render service>

Usage:
    python push_public_db.py                    # uses ./public.db
    python push_public_db.py --file public.db
"""

import os
import sys
import argparse
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass


def push(file_path: Path, site_url: str, token: str):
    url = site_url.rstrip("/") + "/ingest/db"
    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            files={"db_file": (file_path.name, f, "application/octet-stream")},
            timeout=120,
        )
    print(f"POST {url} -> {resp.status_code}")
    print(resp.text)
    resp.raise_for_status()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(_ROOT / "public.db"))
    args = ap.parse_args()

    site_url = os.getenv("LIVE_SITE_URL")
    token    = os.getenv("INGEST_TOKEN")
    if not site_url or not token:
        print("Set LIVE_SITE_URL and INGEST_TOKEN in .env first.")
        sys.exit(1)

    push(Path(args.file), site_url, token)
