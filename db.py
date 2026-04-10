"""
db.py — SQLite schema for Sansad / Parliament Search
Stores sessions, sitting dates, and every attributed statement from debate PDFs.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "sansad.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # ── Parliament Sessions ───────────────────────────────────────────────────
    # One row per session (e.g. "18th Lok Sabha, Session 4 — Budget Session 2025")
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lok_sabha_no    INTEGER NOT NULL,           -- e.g. 18
            session_no      INTEGER NOT NULL,           -- e.g. 4
            session_name    TEXT    NOT NULL,           -- e.g. "Budget Session 2025"
            session_type    TEXT    NOT NULL,           -- 'budget'|'winter'|'monsoon'|'special'
            start_date      TEXT    NOT NULL,           -- ISO: 2025-01-31
            end_date        TEXT,                       -- ISO: 2025-04-04 (null if ongoing)
            total_sittings  INTEGER,                    -- confirmed count from PRS/PIB
            notes           TEXT,                       -- context, disruptions, anchors, etc.
            UNIQUE(lok_sabha_no, session_no)
        )
    """)

    # ── Sitting Dates ─────────────────────────────────────────────────────────
    # One row per calendar day parliament sat. Tracks download and parse status.
    c.execute("""
        CREATE TABLE IF NOT EXISTS sitting_dates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,
            sitting_date    TEXT    NOT NULL,           -- ISO: 2025-03-19
            sitting_number  INTEGER,                    -- ordinal within session (1, 2, 3...)
            has_debate_pdf  INTEGER NOT NULL DEFAULT 0, -- 1 = PDF confirmed available
            source_pdf_id   INTEGER REFERENCES source_pdfs(id),
            notes           TEXT,                       -- e.g. "Holi — adjourned early"
            UNIQUE(sitting_date, lok_sabha_no, session_no)
        )
    """)

    # ── Source PDFs ───────────────────────────────────────────────────────────
    # One row per PDF file downloaded from eparlib.
    c.execute("""
        CREATE TABLE IF NOT EXISTS source_pdfs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,
            sitting_date    TEXT    NOT NULL,           -- ISO: 2025-03-19
            pdf_type        TEXT    NOT NULL,           -- 'fullday' | 'part1' | 'part2'
            filename_type   TEXT    NOT NULL DEFAULT 'UCD',  -- 'UCD' (uncorrected) | 'lsd' (final)
            language        TEXT    NOT NULL DEFAULT 'english',
            url             TEXT    NOT NULL UNIQUE,
            filename        TEXT    NOT NULL,
            doc_id          INTEGER,                    -- eparlib DSpace document ID
            downloaded_at   TEXT,                       -- ISO datetime
            parse_status    TEXT    DEFAULT 'pending'  -- 'pending'|'done'|'error'
        )
    """)

    # ── Members of Parliament ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            name_normalized TEXT NOT NULL,              -- lowercase, stripped of titles
            party           TEXT,
            constituency    TEXT,
            house           TEXT DEFAULT 'lok_sabha',
            UNIQUE(name_normalized, house)
        )
    """)

    # ── Core fact table: one row per attributed statement ────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS statements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,

            -- WHO
            member_id       INTEGER REFERENCES members(id),
            speaker_raw     TEXT NOT NULL,              -- raw text: "SHRI RAHUL GANDHI (WAYANAD)"

            -- WHEN
            sitting_date    TEXT NOT NULL,              -- ISO: 2025-03-19
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,

            -- WHAT
            statement_type  TEXT NOT NULL,              -- 'speech'|'question'|'answer'|'interruption'|'ruling'
            topic           TEXT,                       -- bill / subject being debated (if extractable)
            statement_text  TEXT NOT NULL,

            -- WHERE IN SOURCE
            source_pdf_id   INTEGER REFERENCES source_pdfs(id),
            page_number     INTEGER,
            char_offset     INTEGER,                    -- position in extracted text

            -- METADATA
            language        TEXT DEFAULT 'english',
            word_count      INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Indexes ───────────────────────────────────────────────────────────────
    c.execute("CREATE INDEX IF NOT EXISTS idx_sitting_dates_date    ON sitting_dates(sitting_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sitting_dates_session ON sitting_dates(lok_sabha_no, session_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_statements_member     ON statements(member_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_statements_date       ON statements(sitting_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_statements_session    ON statements(lok_sabha_no, session_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_statements_type       ON statements(statement_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_members_name          ON members(name_normalized)")

    # ── Full-text search (FTS5) on statement text ─────────────────────────────
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS statements_fts
        USING fts5(
            statement_text,
            speaker_raw,
            topic,
            content='statements',
            content_rowid='id'
        )
    """)

    c.execute("""
        CREATE TRIGGER IF NOT EXISTS statements_ai
        AFTER INSERT ON statements BEGIN
            INSERT INTO statements_fts(rowid, statement_text, speaker_raw, topic)
            VALUES (new.id, new.statement_text, new.speaker_raw, new.topic);
        END
    """)

    conn.commit()
    conn.close()
    print(f"✓ Database schema ready at: {DB_PATH}")

    # Seed sessions and sitting dates from sessions_data.py
    _seed_sessions()


def _seed_sessions():
    """Populate sessions and sitting_dates tables from sessions_data.py."""
    from sessions_data import ALL_SESSIONS

    conn = get_connection()
    c = conn.cursor()
    sessions_added = 0
    dates_added = 0

    for session in ALL_SESSIONS:
        # Upsert session row
        c.execute("""
            INSERT INTO sessions
                (lok_sabha_no, session_no, session_name, session_type,
                 start_date, end_date, total_sittings, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lok_sabha_no, session_no) DO UPDATE SET
                session_name   = excluded.session_name,
                session_type   = excluded.session_type,
                start_date     = excluded.start_date,
                end_date       = excluded.end_date,
                total_sittings = excluded.total_sittings,
                notes          = excluded.notes
        """, (
            session["lok_sabha_no"],
            session["session_no"],
            session["session_name"],
            session["session_type"],
            session["start_date"],
            session.get("end_date"),
            session.get("total_sittings"),
            session.get("notes"),
        ))

        c.execute("""
            SELECT id FROM sessions
            WHERE lok_sabha_no = ? AND session_no = ?
        """, (session["lok_sabha_no"], session["session_no"]))
        session_id = c.fetchone()["id"]
        sessions_added += 1

        # Upsert each sitting date
        for i, date_str in enumerate(session["sitting_dates"], start=1):
            c.execute("""
                INSERT INTO sitting_dates
                    (session_id, lok_sabha_no, session_no, sitting_date, sitting_number)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sitting_date, lok_sabha_no, session_no) DO NOTHING
            """, (
                session_id,
                session["lok_sabha_no"],
                session["session_no"],
                date_str,
                i,
            ))
            if c.rowcount:
                dates_added += 1

    conn.commit()
    conn.close()
    print(f"✓ Sessions seeded: {sessions_added} sessions, {dates_added} sitting dates")


def get_sitting_dates_summary():
    """Print a quick summary of sitting dates and their download status."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT
            s.session_name,
            s.session_type,
            COUNT(sd.id)                                    AS total_dates,
            SUM(sd.has_debate_pdf)                          AS downloaded,
            COUNT(sd.id) - SUM(sd.has_debate_pdf)          AS pending
        FROM sitting_dates sd
        JOIN sessions s ON sd.session_id = s.id
        GROUP BY s.id
        ORDER BY s.lok_sabha_no, s.session_no
    """)
    rows = c.fetchall()
    conn.close()

    print(f"\n{'='*65}")
    print("📅  Sitting Dates — Download Status")
    print(f"{'='*65}")
    print(f"  {'Session':<35} {'Type':<10} {'Total':>5} {'Done':>5} {'Pending':>7}")
    print(f"  {'-'*35} {'-'*10} {'-'*5} {'-'*5} {'-'*7}")
    for row in rows:
        print(f"  {row['session_name']:<35} {row['session_type']:<10} "
              f"{row['total_dates']:>5} {row['downloaded']:>5} {row['pending']:>7}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    init_db()
    get_sitting_dates_summary()
