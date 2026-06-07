"""
app/search_bp.py -- Unified search Blueprint

Handles /search with 4 modes: date | politician | party | text
Register in app.py: app.register_blueprint(search_bp)
"""
from flask import Blueprint, render_template, request
from core.db import get_connection
from app.query import (
    full_text_search, get_speakers_list, get_latest_dates,
    get_parties_list, search_by_party, get_date_summary,
    search_by_speaker,
)

search_bp = Blueprint("search_bp", __name__)


def _ticker():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT sitting_date, COUNT(*) as n FROM statements
                 GROUP BY sitting_date ORDER BY sitting_date DESC LIMIT 1""")
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return f"Latest: {row['sitting_date']}  ·  {row['n']} statements"


@search_bp.route("/search")
def search():
    mode    = request.args.get("mode", "").strip()
    q       = request.args.get("q", "").strip()
    date    = request.args.get("date", "").strip()
    party   = request.args.get("party", "").strip()
    speaker = request.args.get("speaker", "").strip()
    session = request.args.get("session", "").strip()
    stype   = request.args.get("type", "").strip()

    results       = []
    total         = 0
    date_summary  = None
    party_members = []
    searched      = False

    # ── Date mode ─────────────────────────────────────────────────────────
    if mode == "date" and date:
        searched     = True
        date_summary = get_date_summary(date)
        conn = get_connection()
        c    = conn.cursor()
        if q:
            sql    = """SELECT s.speaker_raw, s.sitting_date, s.session_no,
                       s.statement_type, s.statement_text, s.original_text,
                       s.word_count, m.name_normalized, m.constituency, m.party,
                       s.original_language
                FROM statements_fts
                JOIN statements s ON statements_fts.rowid = s.id
                JOIN members m    ON s.member_id = m.id
                WHERE statements_fts MATCH ? AND s.sitting_date = ?"""
            params = [q, date]
        else:
            sql    = """SELECT s.speaker_raw, s.sitting_date, s.session_no,
                       s.statement_type, s.statement_text, s.original_text,
                       s.word_count, m.name_normalized, m.constituency, m.party,
                       s.original_language
                FROM statements s JOIN members m ON s.member_id = m.id
                WHERE s.sitting_date = ?"""
            params = [date]
        if party:
            sql += " AND m.party = ?"
            params.append(party)
        if speaker:
            sql += " AND m.name_normalized LIKE ?"
            params.append(f"%{speaker}%")
        c.execute(f"SELECT COUNT(*) FROM ({sql})", params)
        total = c.fetchone()[0]
        c.execute(sql + " ORDER BY s.page_number ASC LIMIT 150", params)
        results = [dict(r) for r in c.fetchall()]
        conn.close()

    # ── Politician mode ────────────────────────────────────────────────────
    elif mode == "politician" and speaker:
        searched = True
        if q:
            results, total = full_text_search(query_text=q, speaker=speaker, limit=150)
        else:
            results = search_by_speaker(speaker, limit=150)
            total   = len(results)

    # ── Party mode ─────────────────────────────────────────────────────────
    elif mode == "party" and party:
        searched              = True
        party_members, results = search_by_party(
            party=party, date_str=date or None, query_text=q or None, limit=150)
        if speaker:
            results = [r for r in results
                       if speaker.lower() in (r.get("name_normalized") or "")]
        total = len(results)

    # ── Free text mode ─────────────────────────────────────────────────────
    elif mode == "text" and q:
        searched       = True
        results, total = full_text_search(
            query_text=q, speaker=speaker or None,
            session=int(session) if session else None,
            stype=stype or None, limit=150)

    # ── Legacy (no mode) ──────────────────────────────────────────────────
    elif q or speaker:
        searched       = True
        mode           = "text" if q else "politician"
        results, total = full_text_search(
            query_text=q or None, speaker=speaker or None, limit=150)

    return render_template(
        "search.html",
        active_tab    = "search",
        mode          = mode,
        q             = q,
        date          = date,
        party         = party,
        party_filter  = party,
        speaker       = speaker,
        searched      = searched,
        results       = results,
        total         = total,
        date_summary  = date_summary,
        party_members = party_members,
        all_speakers  = get_speakers_list(),
        all_parties   = get_parties_list(),
        all_dates     = get_latest_dates(limit=50),
        ticker_text   = _ticker(),
    )
