"""
app/query.py — Search functions used by both the Flask app and CLI

Usage (CLI):
    python app/query.py --speaker "Rahul Gandhi"
    python app/query.py --search "education bill"
    python app/query.py --stats
"""

import sys
import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection


def search_by_speaker(name: str, from_date: str = None, to_date: str = None,
                      limit: int = 20) -> list[dict]:
    conn = get_connection()
    c    = conn.cursor()

    sql    = """
        SELECT s.sitting_date, s.speaker_raw, m.constituency, m.party,
               s.statement_type, s.statement_text, s.word_count, s.page_number,
               p.filename, s.original_language
        FROM statements s
        JOIN members m     ON s.member_id   = m.id
        JOIN source_pdfs p ON s.source_pdf_id = p.id
        WHERE m.name_normalized LIKE ?
    """
    params = [f"%{name.lower()}%"]

    if from_date:
        sql   += " AND s.sitting_date >= ?"
        params.append(from_date)
    if to_date:
        sql   += " AND s.sitting_date <= ?"
        params.append(to_date)

    sql += " ORDER BY s.sitting_date DESC, s.page_number ASC LIMIT ?"
    params.append(limit)

    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def full_text_search(query_text: str, speaker: str = None,
                     session: int = None, stype: str = None,
                     limit: int = 50) -> tuple[list[dict], int]:
    """
    FTS5 search over statement text.
    Returns (results, total_count).
    """
    conn = get_connection()
    c    = conn.cursor()

    if query_text:
        sql    = """
            SELECT s.speaker_raw, s.sitting_date, s.session_no,
                   s.statement_type, s.statement_text, s.word_count,
                   m.constituency, m.name_normalized, s.original_language
            FROM statements_fts
            JOIN statements s ON statements_fts.rowid = s.id
            JOIN members m    ON s.member_id = m.id
            WHERE statements_fts MATCH ?
        """
        params = [query_text]
    else:
        sql    = """
            SELECT s.speaker_raw, s.sitting_date, s.session_no,
                   s.statement_type, s.statement_text, s.word_count,
                   m.constituency, m.name_normalized, s.original_language
            FROM statements s
            JOIN members m ON s.member_id = m.id
            WHERE 1=1
        """
        params = []

    if speaker:
        sql   += " AND m.name_normalized LIKE ?"
        params.append(f"%{speaker}%")
    if session:
        sql   += " AND s.session_no = ?"
        params.append(int(session))
    if stype:
        sql   += " AND s.statement_type = ?"
        params.append(stype)

    count_sql = f"SELECT COUNT(*) FROM ({sql})"
    c.execute(count_sql, params)
    total = c.fetchone()[0]

    sql += " ORDER BY s.sitting_date DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows, total


def get_stats() -> dict:
    conn = get_connection()
    c    = conn.cursor()

    c.execute("SELECT COUNT(*) as n FROM source_pdfs WHERE parse_status='done'")
    pdfs = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM statements")
    stmts = c.fetchone()["n"]

    c.execute("SELECT COUNT(*) as n FROM members")
    members = c.fetchone()["n"]

    c.execute("""
        SELECT m.name, COUNT(*) as cnt
        FROM statements s JOIN members m ON s.member_id = m.id
        GROUP BY m.id ORDER BY cnt DESC LIMIT 10
    """)
    top_speakers = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT sitting_date, COUNT(*) as cnt
        FROM statements GROUP BY sitting_date ORDER BY sitting_date DESC
    """)
    by_date = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "pdfs_parsed":    pdfs,
        "total_stmts":    stmts,
        "unique_speakers": members,
        "top_speakers":   top_speakers,
        "by_date":        by_date,
    }


def get_speakers_list() -> list[dict]:
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT m.name, m.name_normalized, m.constituency, m.party,
               COUNT(s.id) as stmt_count
        FROM members m
        LEFT JOIN statements s ON s.member_id = m.id
        GROUP BY m.id
        ORDER BY stmt_count DESC, m.name ASC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_latest_dates(limit: int = 10) -> list[dict]:
    """Return the most recent sitting dates that have statements."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT
            s.sitting_date,
            ss.session_name,
            ss.session_type,
            COUNT(st.id) as stmt_count,
            COUNT(DISTINCT st.member_id) as speaker_count
        FROM sitting_dates s
        JOIN sessions ss ON s.session_id = ss.id
        LEFT JOIN statements st ON st.sitting_date = s.sitting_date
        WHERE s.has_debate_pdf = 1
        GROUP BY s.sitting_date
        HAVING stmt_count > 0
        ORDER BY s.sitting_date DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_trending_topics(from_date: str = None, limit: int = 8) -> list[dict]:
    """Return topics with the most statements in recent period."""
    conn = get_connection()
    c    = conn.cursor()
    sql  = """
        SELECT topic, COUNT(*) as cnt, MAX(sitting_date) as last_seen
        FROM statements
        WHERE topic IS NOT NULL
    """
    params = []
    if from_date:
        sql   += " AND sitting_date >= ?"
        params.append(from_date)
    sql += " GROUP BY topic ORDER BY cnt DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_statements_for_date(date_str: str, limit: int = 60) -> list[dict]:
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT s.speaker_raw, s.statement_type, s.statement_text,
               s.word_count, s.page_number, s.topic, s.original_language,
               m.constituency, m.party
        FROM statements s
        JOIN members m ON s.member_id = m.id
        WHERE s.sitting_date = ?
          AND s.statement_type IN ('speech', 'answer', 'question')
          AND s.word_count >= 20
        ORDER BY s.page_number ASC
        LIMIT ?
    """, (date_str, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_statements_for_topic(topic_query: str, limit: int = 40) -> list[dict]:
    """FTS search restricted to topic-bearing statements."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT s.speaker_raw, s.sitting_date, s.session_no,
               s.statement_type, s.statement_text, s.word_count,
               m.constituency, m.party, s.original_language
        FROM statements_fts
        JOIN statements s ON statements_fts.rowid = s.id
        JOIN members m    ON s.member_id = m.id
        WHERE statements_fts MATCH ?
          AND s.word_count >= 20
        ORDER BY s.sitting_date DESC, rank
        LIMIT ?
    """, (topic_query, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Search Sansad parliament database")
    ap.add_argument("--speaker",  help="Search by MP name")
    ap.add_argument("--search",   help="Full text search")
    ap.add_argument("--from",     dest="from_date", help="From date (YYYY-MM-DD)")
    ap.add_argument("--to",       dest="to_date",   help="To date (YYYY-MM-DD)")
    ap.add_argument("--limit",    type=int, default=20)
    ap.add_argument("--stats",    action="store_true")
    args = ap.parse_args()

    if args.stats:
        stats = get_stats()
        print(f"\n📊 Database Stats")
        print(f"  PDFs parsed:      {stats['pdfs_parsed']}")
        print(f"  Total statements: {stats['total_stmts']}")
        print(f"  Unique speakers:  {stats['unique_speakers']}")
        print(f"\n  Top speakers:")
        for s in stats["top_speakers"]:
            print(f"    {s['name']:<35} {s['cnt']:>4}")
        print(f"\n  By date:")
        for d in stats["by_date"]:
            print(f"    {d['sitting_date']}  →  {d['cnt']} statements")

    elif args.speaker:
        rows = search_by_speaker(args.speaker, args.from_date, args.to_date, args.limit)
        if not rows:
            print(f"No statements found for: '{args.speaker}'")
        for r in rows:
            print(f"\n📅 {r['sitting_date']}  |  {r['speaker_raw']}")
            print(f"   Type: {r['statement_type'].upper()}  |  {r['word_count']} words")
            print(f"   {r['statement_text'][:300]}...")

    elif args.search:
        rows, total = full_text_search(args.search, limit=args.limit)
        print(f"\nSearch: '{args.search}' — {total} results")
        for r in rows:
            print(f"\n📅 {r['sitting_date']}  |  {r['speaker_raw']}")
            print(f"   {r['statement_text'][:300]}...")

    else:
        ap.print_help()
