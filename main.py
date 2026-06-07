"""
main.py — Run the full Sansad pipeline

Steps:
  1. Initialise DB + seed sessions/sitting dates
  2. Download PDFs for target dates (defaults to next 5 pending in Session 4)
  3. Parse each downloaded PDF into attributed statements
  4. Auto-generate AI digests (new dates) + top-10 politician profiles

Usage:
    python main.py                              # 5 pending dates, Session 4
    python main.py --session 3                  # 5 pending dates, Session 3
    python main.py --session 2 --max-pdfs 10    # up to 10 pending dates, Session 2
    python main.py --all-sessions               # all pending dates across all sessions
    python main.py --dates 2025-03-19 2025-03-18
    python main.py --parse-only                 # re-parse already downloaded PDFs
    python main.py --status                     # show sitting date download status
    python main.py --no-ai                      # skip AI generation step
"""

import argparse
import sys
import os
from pathlib import Path

# Load .env from project root (works on Windows without shell export)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from db import init_db, get_connection, get_sitting_dates_summary
from scraper import run_scraper
from parser import parse_pdf_file
from sessions_data import ALL_SESSIONS

PDF_DIR = Path(__file__).parent / "pdfs"


def run_pipeline(dates=None, parse_only=False, translate=False, max_pdfs=5,
                 lok_sabha=18, session=4, all_sessions=False, skip_ai=False):

    print("\nSansad Parliament Data Pipeline")
    print("=" * 60)

    # Step 1 -- Init DB (also seeds sessions + sitting_dates)
    init_db()

    # Step 2 -- Download PDFs
    if not parse_only:
        if all_sessions:
            for s in ALL_SESSIONS:
                run_scraper(
                    dates=None,
                    lok_sabha=s["lok_sabha_no"],
                    session=s["session_no"],
                    max_pdfs=max_pdfs,
                )
        else:
            run_scraper(
                dates=dates,
                lok_sabha=lok_sabha,
                session=session,
                max_pdfs=max_pdfs,
            )

    # Step 3 -- Parse any PDFs not yet parsed
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT * FROM source_pdfs
        WHERE parse_status IN ('pending', 'error')
        ORDER BY sitting_date DESC
    """)
    pending = [dict(row) for row in c.fetchall()]
    conn.close()

    print(f"\nPDFs pending parse: {len(pending)}")

    total_statements = 0
    for pdf_record in pending:
        local_path = PDF_DIR / pdf_record["filename"]
        if local_path.exists():
            result = parse_pdf_file(str(local_path), pdf_record, translate=translate)
            total_statements += result.get("stored", 0) if isinstance(result, dict) else result
        else:
            print(f"  PDF not found locally: {pdf_record['filename']}")

    print(f"\n{'='*60}")
    print(f"Pipeline complete")
    print(f"  Statements extracted this run: {total_statements}")
    print(f"  Database: sansad.db")

    # Step 4 -- Auto-generate AI content (digests + top-10 profiles)
    if not skip_ai and os.getenv("ANTHROPIC_API_KEY"):
        _run_ai_generation()
    elif not os.getenv("ANTHROPIC_API_KEY"):
        print("\n[AI] Skipping -- ANTHROPIC_API_KEY not set")

    print(f"\nQuery your data:")
    print(f"   python query.py --stats")
    print(f"   python query.py --speaker \"Rahul Gandhi\"")
    print(f"   python query.py --search \"education\"")
    print(f"   python main.py --status")
    print(f"{'='*60}\n")


def _run_ai_generation():
    """Generate digests for undone dates + profiles for top-10 MPs by statement count."""
    try:
        from app.digest import generate_digest_for_date, generate_politician_profile
    except ImportError as e:
        print(f"\n[AI] Could not import digest module: {e}")
        return

    conn = get_connection()
    c    = conn.cursor()

    # Dates with statements but no digest yet
    c.execute("""
        SELECT DISTINCT s.sitting_date FROM statements s
        LEFT JOIN digests d ON d.sitting_date = s.sitting_date
        WHERE d.id IS NULL
        ORDER BY s.sitting_date DESC
    """)
    undone_dates = [r[0] for r in c.fetchall()]

    # Top 10 MPs by statement count that don't have a profile yet
    c.execute("""
        SELECT m.id, m.name, COUNT(s.id) as cnt
        FROM members m
        JOIN statements s ON s.member_id = m.id
        LEFT JOIN politician_profiles p ON p.member_id = m.id
        WHERE p.id IS NULL
        GROUP BY m.id
        ORDER BY cnt DESC
        LIMIT 10
    """)
    top_mps = [{"id": r[0], "name": r[1], "cnt": r[2]} for r in c.fetchall()]
    conn.close()

    print(f"\n[AI] Generating digests for {len(undone_dates)} date(s)...")
    for date_str in undone_dates:
        print(f"  {date_str}... ", end="", flush=True)
        result = generate_digest_for_date(date_str)
        print("done" if result else "no data")

    print(f"[AI] Generating profiles for top {len(top_mps)} MP(s) by statement count...")
    for mp in top_mps:
        print(f"  {mp['name']} ({mp['cnt']} stmts)... ", end="", flush=True)
        result = generate_politician_profile(mp["id"])
        print("done" if result else "no data")


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
    parser.add_argument("--translate",    action="store_true",
                        help="Run Sarvam AI translation on Hindi/regional statements")
    parser.add_argument("--max-pdfs",     type=int, default=5,
                        help="Max PDFs to download per session (default: 5)")
    parser.add_argument("--status",       action="store_true",
                        help="Show sitting date download status and exit")
    parser.add_argument("--no-ai",        action="store_true",
                        help="Skip AI digest + profile generation step")
    args = parser.parse_args()

    if args.status:
        init_db()
        get_sitting_dates_summary()
    else:
        run_pipeline(
            dates=args.dates,
            parse_only=args.parse_only,
            translate=args.translate,
            max_pdfs=args.max_pdfs,
            lok_sabha=args.lok_sabha,
            session=args.session,
            all_sessions=args.all_sessions,
            skip_ai=args.no_ai,
        )
