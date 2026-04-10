"""
main.py — Run the full Sansad pipeline

Steps:
  1. Initialise DB + seed sessions/sitting dates
  2. Download PDFs for target dates (defaults to next 5 pending in Session 4)
  3. Parse each downloaded PDF into attributed statements

Usage:
    python main.py                              # 5 pending dates, Session 4
    python main.py --session 3                  # 5 pending dates, Session 3
    python main.py --session 2 --max-pdfs 10    # up to 10 pending dates, Session 2
    python main.py --all-sessions               # all pending dates across all sessions
    python main.py --dates 2025-03-19 2025-03-18
    python main.py --parse-only                 # re-parse already downloaded PDFs
    python main.py --status                     # show sitting date download status
"""

import argparse
from pathlib import Path

from db import init_db, get_connection, get_sitting_dates_summary
from scraper import run_scraper
from parser import parse_pdf_file
from sessions_data import ALL_SESSIONS

PDF_DIR = Path(__file__).parent / "pdfs"


def run_pipeline(dates=None, parse_only=False, max_pdfs=5,
                 lok_sabha=18, session=4, all_sessions=False):

    print("\n🏛  Sansad Parliament Data Pipeline")
    print("=" * 60)

    # Step 1 — Init DB (also seeds sessions + sitting_dates)
    init_db()

    # Step 2 — Download PDFs
    if not parse_only:
        if all_sessions:
            all_downloaded = []
            for s in ALL_SESSIONS:
                downloaded = run_scraper(
                    dates=None,
                    lok_sabha=s["lok_sabha_no"],
                    session=s["session_no"],
                    max_pdfs=max_pdfs,
                )
                all_downloaded.extend(downloaded)
        else:
            run_scraper(
                dates=dates,
                lok_sabha=lok_sabha,
                session=session,
                max_pdfs=max_pdfs,
            )

    # Step 3 — Parse any PDFs not yet parsed
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT * FROM source_pdfs
        WHERE parse_status IN ('pending', 'error')
        ORDER BY sitting_date DESC
    """)
    pending = [dict(row) for row in c.fetchall()]
    conn.close()

    print(f"\n📄 PDFs pending parse: {len(pending)}")

    total_statements = 0
    for pdf_record in pending:
        local_path = PDF_DIR / pdf_record["filename"]
        if local_path.exists():
            count = parse_pdf_file(str(local_path), pdf_record)
            total_statements += count
        else:
            print(f"  ✗ PDF not found locally: {pdf_record['filename']}")

    print(f"\n{'='*60}")
    print(f"✅ Pipeline complete")
    print(f"   Statements extracted this run: {total_statements}")
    print(f"   Database: sansad.db")
    print(f"\nQuery your data:")
    print(f"   python query.py --stats")
    print(f"   python query.py --speaker \"Rahul Gandhi\"")
    print(f"   python query.py --search \"education\"")
    print(f"   python main.py --status")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sansad Parliament Data Pipeline")
    parser.add_argument("--dates",        nargs="+",      help="Specific sitting dates (YYYY-MM-DD)")
    parser.add_argument("--session",      type=int, default=4,
                        help="Session number to scrape (default: 4)")
    parser.add_argument("--lok-sabha",    type=int, default=18,
                        help="Lok Sabha number (default: 18)")
    parser.add_argument("--all-sessions", action="store_true",
                        help="Scrape all known sessions (overrides --session)")
    parser.add_argument("--parse-only",   action="store_true",
                        help="Skip download; re-parse existing PDFs only")
    parser.add_argument("--max-pdfs",     type=int, default=5,
                        help="Max PDFs to download per session (default: 5)")
    parser.add_argument("--status",       action="store_true",
                        help="Show sitting date download status and exit")
    args = parser.parse_args()

    if args.status:
        init_db()
        get_sitting_dates_summary()
    else:
        run_pipeline(
            dates=args.dates,
            parse_only=args.parse_only,
            max_pdfs=args.max_pdfs,
            lok_sabha=args.lok_sabha,
            session=args.session,
            all_sessions=args.all_sessions,
        )
