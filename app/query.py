"""
app/query.py — Search functions used by both the Flask app and CLI

Usage (CLI):
    python app/query.py --speaker "Rahul Gandhi"
    python app/query.py --search "education bill"
    python app/query.py --stats
"""

import sys
import argparse
import re
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection


_NEWS_STOPWORDS = {
    "about", "above", "after", "again", "against", "along", "also", "among",
    "asked", "being", "been", "between", "chairperson", "country", "details", "during", "following", "from",
    "government", "house", "india", "indian", "minister", "ministry", "other",
    "have", "honourable", "lok", "madam", "many", "member", "members",
    "parliament", "pleased", "present", "regarding", "state", "states", "their",
    "thereof", "these", "that", "this", "they", "them", "under", "whether",
    "which", "while", "will", "with", "would", "pradesh", "question", "sabha",
    "scheme", "shri", "shrimati", "sir", "through", "years",
}

_THEME_RULES = [
    ("Vande Mataram", ("vande mataram", "national song", "bankim", "tagore")),
    ("Budget and finance", ("budget", "finance bill", "tax", "gst", "tds", "jan dhan", "crypto")),
    ("Labour and jobs", ("labour", "employment", "unemployment", "workers", "pension", "shram shakti")),
    ("Education", ("education", "university", "nep", "school", "students")),
    ("Environment", ("environment", "forest", "climate", "emissions", "pollution", "carbon")),
    ("Culture and heritage", ("culture", "archaeological", "keeladi", "civilisation", "heritage")),
    ("Sports", ("sports", "athletes", "training", "youth affairs")),
    ("Corporate affairs", ("corporate", "csr", "companies", "investor", "niveshak")),
]


def _clean_snippet(text: str, max_chars: int = 300) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut}..."


def _extract_terms(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", text or "")
    counts = Counter(w.lower() for w in words if w.lower() not in _NEWS_STOPWORDS)
    return [w for w, _ in counts.most_common(limit)]


def _infer_theme(text: str) -> str:
    low = (text or "").lower()
    for label, needles in _THEME_RULES:
        if any(n in low for n in needles):
            return label
    terms = _extract_terms(text, 1)
    return terms[0].title() if terms else "Parliament proceedings"


def _headline_for_statement(row: dict) -> str:
    text = row.get("statement_text") or ""
    theme = _infer_theme(text)
    speaker = (row.get("speaker_raw") or "A member").title()
    stype = row.get("statement_type")

    minister = re.search(r"Will the Minister of ([A-Z ,&-]+?) be pleased", text)
    if minister:
        ministry = minister.group(1).title()
        ministry_low = ministry.lower()
        if "sports" in ministry_low:
            theme = "Sports"
        elif "culture" in ministry_low:
            theme = "Culture and heritage"
        elif "education" in ministry_low:
            theme = "Education"
        elif "labour" in ministry_low or "employment" in ministry_low:
            theme = "Labour and jobs"
        elif "environment" in ministry_low or "forest" in ministry_low:
            theme = "Environment"
        elif "finance" in ministry_low:
            theme = "Budget and finance"
        elif "corporate" in ministry_low:
            theme = "Corporate affairs"
        row["theme"] = theme
        return f"{ministry} faces questions on {theme.lower()}"

    if "finance bill" in text.lower():
        return "Finance Bill reaches the House"
    if "vande mataram" in text.lower():
        return f"{speaker} joins Vande Mataram anniversary debate"
    if stype == "question":
        return f"{speaker} raises {theme.lower()}"
    return f"{speaker} speaks on {theme.lower()}"


def _related_older_items(current: dict, candidates: list[dict], limit: int = 3) -> list[dict]:
    current_terms = set(_extract_terms(current.get("statement_text", ""), 12))
    current_speaker = (current.get("speaker_raw") or "").lower()
    current_theme = current.get("theme") or _infer_theme(current.get("statement_text", ""))
    scored = []

    for row in candidates:
        score = 0
        terms = set(_extract_terms(row.get("statement_text", ""), 12))
        shared = current_terms & terms
        same_speaker = current_speaker and current_speaker == (row.get("speaker_raw") or "").lower()
        same_theme = current_theme == _infer_theme(row.get("statement_text", ""))
        if not same_speaker and not same_theme:
            continue
        score += len(shared) * 2
        if same_speaker:
            score += 5
        if same_theme:
            score += 3
        if score:
            item = dict(row)
            item["shared_terms"] = sorted(shared)[:4]
            item["theme"] = _infer_theme(row.get("statement_text", ""))
            item["teaser"] = _clean_snippet(row.get("statement_text", ""), 150)
            scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], x[1]["sitting_date"]))
    deduped = []
    seen = set()
    for _, item in scored:
        key = (item["sitting_date"], item["speaker_raw"], item["theme"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def search_by_speaker(name: str, from_date: str = None, to_date: str = None,
                      limit: int = 20) -> list[dict]:
    conn = get_connection()
    c    = conn.cursor()

    sql    = """
        SELECT s.sitting_date, s.speaker_raw, m.constituency, m.party,
               s.statement_type, s.statement_text, s.original_text,
               s.word_count, s.page_number,
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
                     pdf_id: int = None,
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
                   s.statement_type, s.statement_text, s.original_text,
                   s.word_count, m.constituency, m.name_normalized,
                   s.original_language
            FROM statements_fts
            JOIN statements s ON statements_fts.rowid = s.id
            JOIN members m    ON s.member_id = m.id
            WHERE statements_fts MATCH ?
        """
        params = [query_text]
    else:
        sql    = """
            SELECT s.speaker_raw, s.sitting_date, s.session_no,
                   s.statement_type, s.statement_text, s.original_text,
                   s.word_count, m.constituency, m.name_normalized,
                   s.original_language
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
    if pdf_id:
        sql   += " AND s.source_pdf_id = ?"
        params.append(int(pdf_id))

    count_sql = f"SELECT COUNT(*) FROM ({sql})"
    c.execute(count_sql, params)
    total = c.fetchone()[0]

    sql += " ORDER BY s.sitting_date DESC, s.page_number ASC LIMIT ?"
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
    """Return the most recent sitting dates that have parsed statements.
    Queries statements table directly — works even for PDFs registered via
    local_scan.py where sitting_dates.has_debate_pdf may not be set.
    """
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT
            st.sitting_date,
            COALESCE(ss.session_name, 'Session ' || st.session_no) as session_name,
            COALESCE(ss.session_type, '')                           as session_type,
            COUNT(DISTINCT st.id)        as stmt_count,
            COUNT(DISTINCT st.member_id) as speaker_count
        FROM statements st
        LEFT JOIN sessions ss
               ON ss.lok_sabha_no = st.lok_sabha_no
              AND ss.session_no   = st.session_no
        GROUP BY st.sitting_date
        ORDER BY st.sitting_date DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_parsed_pdfs() -> list[dict]:
    """Return all source PDFs that have been parsed, with statement counts."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT
            sp.id, sp.filename, sp.sitting_date, sp.language,
            sp.session_no, sp.lok_sabha_no, sp.filename_type,
            COUNT(s.id)                                                   as stmt_count,
            COUNT(DISTINCT s.member_id)                                   as speaker_count,
            SUM(CASE WHEN s.original_language IS NOT NULL THEN 1 ELSE 0 END) as non_english,
            SUM(CASE WHEN s.original_text     IS NOT NULL THEN 1 ELSE 0 END) as bilingual
        FROM source_pdfs sp
        LEFT JOIN statements s ON s.source_pdf_id = sp.id
        WHERE sp.parse_status = 'done'
        GROUP BY sp.id
        ORDER BY sp.sitting_date DESC
    """)
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
               s.original_text, s.original_language,
               s.word_count, s.page_number, s.topic,
               m.constituency, m.party, m.name_normalized
        FROM statements s
        JOIN members m ON s.member_id = m.id
        WHERE s.sitting_date = ?
          AND s.word_count >= 10
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


def get_news_briefing(limit: int = 12) -> dict:
    """
    Build a local news-style briefing from parsed statements.
    Items come from the latest dates with parsed statements and link to older
    debates by shared subject terms and recurring speakers.
    """
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        SELECT sitting_date, session_no, COUNT(*) AS stmt_count,
               COUNT(DISTINCT member_id) AS speaker_count
        FROM statements
        GROUP BY sitting_date, session_no
        ORDER BY sitting_date DESC
        LIMIT 5
    """)
    recent_dates = [dict(r) for r in c.fetchall()]

    if not recent_dates:
        conn.close()
        return {"has_data": False, "news_items": [], "recent_dates": []}

    latest_date = recent_dates[0]["sitting_date"]
    date_params = [r["sitting_date"] for r in recent_dates[:3]]
    placeholders = ",".join("?" * len(date_params))
    c.execute(f"""
        SELECT s.id, s.sitting_date, s.session_no, s.speaker_raw,
               s.statement_type, s.statement_text, s.word_count, s.page_number,
               s.topic, s.original_language, m.name_normalized, m.constituency,
               m.party, p.filename
        FROM statements s
        JOIN members m ON s.member_id = m.id
        LEFT JOIN source_pdfs p ON s.source_pdf_id = p.id
        WHERE s.sitting_date IN ({placeholders})
          AND s.statement_type IN ('speech', 'answer', 'question')
          AND s.word_count >= 40
        ORDER BY s.sitting_date DESC, s.word_count DESC
        LIMIT ?
    """, (*date_params, limit * 3))
    latest_rows = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT s.id, s.sitting_date, s.session_no, s.speaker_raw,
               s.statement_type, s.statement_text, s.word_count, s.page_number,
               s.topic, s.original_language, m.name_normalized, m.constituency,
               m.party, p.filename
        FROM statements s
        JOIN members m ON s.member_id = m.id
        LEFT JOIN source_pdfs p ON s.source_pdf_id = p.id
        WHERE s.sitting_date < ?
          AND s.statement_type IN ('speech', 'answer', 'question')
          AND s.word_count >= 40
        ORDER BY s.sitting_date DESC, s.word_count DESC
    """, (latest_date,))
    older_rows = [dict(r) for r in c.fetchall()]
    conn.close()

    seen_themes: Counter[str] = Counter()
    items = []
    for row in latest_rows:
        row = dict(row)
        theme = _infer_theme(row["statement_text"])
        if seen_themes[theme] >= 3:
            continue
        seen_themes[theme] += 1
        row["theme"] = theme
        row["headline"] = _headline_for_statement(row)
        theme = row["theme"]
        row["teaser"] = _clean_snippet(row["statement_text"], 360)
        row["terms"] = _extract_terms(row["statement_text"], 5)
        row["related"] = _related_older_items(
            row,
            [older for older in older_rows if older["sitting_date"] < row["sitting_date"]],
            3,
        )
        items.append(row)
        if len(items) >= limit:
            break

    theme_counts = Counter(item["theme"] for item in items)
    return {
        "has_data": True,
        "latest_date": latest_date,
        "recent_dates": recent_dates,
        "news_items": items,
        "themes": [{"theme": t, "cnt": n} for t, n in theme_counts.most_common()],
    }


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
