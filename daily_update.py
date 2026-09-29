"""
daily_update.py — One entry point for the daily local refresh. Meant to be
run by Windows Task Scheduler (or manually).

Steps:
    1. Scrape new debate PDFs (Playwright, headless) — debates_ucd first,
       since UCD files publish within days of a sitting.
    2. Parse + chunk any newly downloaded PDFs into the local sansad.db.
    3. Export the last N days into public.db.
    4. Push public.db to the live site.

The full sansad.db never leaves this machine — only the trimmed public.db
from step 3 goes out, and only to the URL in .env (LIVE_SITE_URL).

Usage:
    python daily_update.py
    python daily_update.py --days 30 --limit 25 --skip-scrape
"""

import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]):
    print(f"\n{'='*60}\n$ {' '.join(cmd)}\n{'='*60}")
    result = subprocess.run(cmd, cwd=str(_ROOT))
    if result.returncode != 0:
        print(f"!! Command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="Days of data to publish")
    ap.add_argument("--limit", type=int, default=25, help="Max catalog/download items per collection")
    ap.add_argument("--skip-scrape", action="store_true", help="Skip scraping, just re-parse/export/push")
    ap.add_argument("--skip-push", action="store_true", help="Build public.db but don't push it")
    args = ap.parse_args()

    print(f"Daily update started {datetime.now().isoformat(timespec='seconds')}")
    py = sys.executable

    if not args.skip_scrape:
        ok = run([
            py, "scrapers/parliament/playwright_scraper.py",
            "--catalog", "--resolve", "--download", "--headless",
            "--collections", "debates_ucd", "debates_en", "debates_hi",
            "--limit", str(args.limit),
        ])
        if not ok:
            print("Scrape step failed — continuing to parse whatever is already downloaded.")

    if not args.skip_scrape:
        # Last 3 days, not just today: PIB backdates and adds late, and the scraper
        # skips anything already stored, so overlap is free.
        if not run([py, "scrapers/pib/pib_scraper.py", "--days", "3"]):
            print("PIB step failed — continuing without fresh PIB data.")
        # Party & leader YouTube — same 3-day overlap; already-stored videos are skipped.
        if not run([py, "scrapers/youtube/youtube_scraper.py", "--days", "3"]):
            print("YouTube step failed — continuing without fresh video transcripts.")

    if not run([py, "main.py", "--parse-only"]):
        print("Parse step failed — aborting (public.db would be stale/incomplete).")
        sys.exit(1)

    if not run([py, "parser/export_public_db.py", "--days", str(args.days)]):
        sys.exit(1)

    if not args.skip_push:
        if not run([py, "push_public_db.py"]):
            sys.exit(1)

    print(f"\nDaily update finished {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
