"""
query.py — Search the parliament database

Usage:
    python query.py --speaker "Rahul Gandhi"
    python query.py --speaker "Rahul Gandhi" --from 2025-03-01 --to 2025-03-31
    python query.py --search "education bill"
    python query.py --stats
"""

import argparse
import sqlite3
from db import get_connection


def search_by_speaker(name: str, from_date: str = None, to_date: str = None,
                      limit: int = 20):
    """Find all statements by an MP."""
    conn = get_connection()
    c = conn.cursor()

    query = """
        SELECT
            s.sitting_date,
            s.speaker_raw,
            m.constituency,
            m.party,
            s.statement_type,
            s.statement_text,
            s.word_count,
            s.page_number,
            p.filename
        FROM statements s
        JOIN members m ON s.member_id = m.id
        JOIN source_pdfs p ON s.source_pdf_id = p.id
        WHERE m.name_normalized LIKE ?
    """
    params = [f"%{name.lower()}%"]

    if from_date:
        query += " AND s.sitting_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND s.sitting_date <= ?"
        params.append(to_date)

    query += " ORDER BY s.sitting_date DESC, s.page_number ASC LIMIT ?"
    params.append(limit)

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print(f"No statements found for: '{name}'")
        return []

    print(f"\n{'='*70}")
    print(f"Statements by: {name.title()} ({len(rows)} results)")
    print(f"{'='*70}")

    for row in rows:
        print(f"\n📅 {row['sitting_date']}  |  {row['speaker_raw']}")
        if row['constituency']:
            print(f"   Constituency: {row['constituency']}")
        print(f"   Type: {row['statement_type'].upper()}  |  {row['word_count']} words  |  Page {row['page_number']}")
        print(f"   Source: {row['filename']}")
        print(f"\n   {row['statement_text'][:400]}...")
        print(f"\n   {'-'*60}")

    return [dict(r) for r in rows]


def full_text_search(query_text: str, limit: int = 10):
    """Search statement text using SQLite FTS5."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        SELECT
            s.sitting_date,
            s.speaker_raw,
            s.statement_type,
            s.statement_text,
            s.page_number,
            p.filename,
            rank
        FROM statements_fts
        JOIN statements s ON statements_fts.rowid = s.id
        JOIN source_pdfs p ON s.source_pdf_id = p.id
        WHERE statements_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query_text, limit))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print(f"No results for: '{query_text}'")
        return []

    print(f"\n{'='*70}")
    print(f"Search results for: '{query_text}' ({len(rows)} results)")
    print(f"{'='*70}")

    for row in rows:
        print(f"\n📅 {row['sitting_date']}  |  {row['speaker_raw']}")
        print(f"   Type: {row['statement_type'].upper()}  |  Page {row['page_number']}")
        print(f"   Source: {row['filename']}")
        print(f"\n   {row['statement_text'][:400]}...")
        print(f"\n   {'-'*60}")

    return [dict(r) for r in rows]


def show_stats():
    """Show database statistics."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as n FROM source_pdfs WHERE parse_status='done'")
    pdfs = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM statements")
    stmts = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM members")
    members = c.fetchone()["n"]

    c.execute("""
        SELECT m.name, COUNT(*) as stmt_count
        FROM statements s JOIN members m ON s.member_id = m.id
        GROUP BY m.id ORDER BY stmt_count DESC LIMIT 10
    """)
    top_speakers = c.fetchall()

    c.execute("""
        SELECT sitting_date, COUNT(*) as stmt_count
        FROM statements GROUP BY sitting_date ORDER BY sitting_date DESC
    """)
    by_date = c.fetchall()

    conn.close()

    print(f"\n{'='*50}")
    print("📊 Sansad Database Stats")
    print(f"{'='*50}")
    print(f"  PDFs parsed:      {pdfs}")
    print(f"  Total statements: {stmts}")
    print(f"  Unique speakers:  {members}")
    print(f"\n  Top speakers:")
    for row in top_speakers:
        print(f"    {row['name']:<35} {row['stmt_count']:>4} statements")
    print(f"\n  Statements by date:")
    for row in by_date:
        print(f"    {row['sitting_date']}  →  {row['stmt_count']} statements")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search Sansad parliament database")
    parser.add_argument("--speaker", help="Search by MP name")
    parser.add_argument("--search",  help="Full text search")
    parser.add_argument("--from",    dest="from_date", help="From date (YYYY-MM-DD)")
    parser.add_argument("--to",      dest="to_date",   help="To date (YYYY-MM-DD)")
    parser.add_argument("--limit",   type=int, default=20)
    parser.add_argument("--stats",   action="store_true")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.speaker:
        search_by_speaker(args.speaker, args.from_date, args.to_date, args.limit)
    elif args.search:
        full_text_search(args.search, args.limit)
    else:
        parser.print_help()
