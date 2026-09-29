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

try:
    # Use the OS certificate store — Python's bundled CAs fail on some Windows
    # setups (antivirus / missing intermediates). Optional: skipped if not installed.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import requests

_ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path):
    """Minimal .env reader — no python-dotenv dependency required."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(_ROOT / ".env")


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
