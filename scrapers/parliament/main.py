"""
scrapers/parliament/main.py — Scraper pipeline entry point

Default mode (no flags): scan local pdfs/ folder, register any new files,
then parse them.  No network calls.

Use --probe to also attempt downloading from eparlib (often blocked; manual
browser download + dropping into pdfs/ is more reliable).

Usage:
    python scrapers/parliament/main.py              # scan local pdfs/ + register
    python scrapers/parliament/main.py --list       # list registered PDFs in DB
    python scrapers/parliament/main.py --status     # session download status
    python scrapers/parliament/main.py --probe                    # try network download
    python scrapers/parliament/main.py --probe --all-sessions     # probe all sessions
    python scrapers/parliament/main.py --probe --dates 2026-03-19
"""

import sys
import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import init_db, get_sitting_dates_summary
from core.sessions_data import get_latest_session
from scrapers.parliament.local_scan import scan_local_pdfs, list_registered_pdfs
from scrapers.parliament.scraper import run_scraper


def main():
    ap = argparse.ArgumentParser(description="Parliament PDF scraper")
    ap.add_argument("--list",         action="store_true",
                    help="List all registered PDFs in DB")
    ap.add_argument("--status",       action="store_true",
                    help="Show sitting date download status")
    ap.add_argument("--probe",        action="store_true",
                    help="Also attempt network download from eparlib (often blocked)")
    ap.add_argument("--dates",        nargs="+", help="Specific sitting dates (YYYY-MM-DD) — requires --probe")
    ap.add_argument("--session",      type=int,  default=None)
    ap.add_argument("--lok-sabha",    type=int,  default=18)
    ap.add_argument("--all-sessions", action="store_true",
                    help="(With --probe) scan all sessions for pending PDFs")
    ap.add_argument("--max-pdfs",     type=int,  default=5)
    args = ap.parse_args()

    init_db()

    if args.list:
        list_registered_pdfs()
        return

    if args.status:
        get_sitting_dates_summary()
        return

    # Always scan local pdfs/ first
    scan_local_pdfs()

    # Optionally attempt network probing (eparlib blocks most scripted requests)
    if args.probe:
        print("\n⚠  Network probe mode — eparlib often blocks downloads.")
        print("   Manually download PDFs and drop them in pdfs/ for reliable ingestion.\n")

        if args.all_sessions:
            run_scraper(dates=None, lok_sabha=args.lok_sabha, session=None,
                        max_pdfs=args.max_pdfs, all_sessions=True)
        else:
            session = args.session
            if session is None and not args.dates:
                latest = get_latest_session(args.lok_sabha)
                session = latest["session_no"]
                print(f"  → Auto-selected: {latest['session_name']} (Session {session})")
            run_scraper(dates=args.dates, lok_sabha=args.lok_sabha, session=session,
                        max_pdfs=args.max_pdfs, all_sessions=False)


if __name__ == "__main__":
    main()
