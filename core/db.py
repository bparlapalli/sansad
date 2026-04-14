"""
core/db.py — SQLite schema for ParamaSrota / Sansad Parliament DB
Stores sessions, sitting dates, and every attributed statement from debate PDFs.

DB lives at the project root (sansad.db) regardless of which sub-package
imports this module.

Virtiofs note:
  When the project folder is mounted via virtiofs (e.g. Windows host on WSL2 /
  Cowork desktop), SQLite cannot use file-locking on the mount.  We detect this
  once, copy the DB to a local temp path for read-write work, and write it back
  in-place after every commit.  Call sync_db() explicitly after bulk operations.
"""

import shutil
import sqlite3
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT    = Path(__file__).resolve().parent.parent
DB_PATH  = _ROOT / "sansad.db"          # canonical location (may be virtiofs)
_WORK_DB = Path(f"/tmp/sansad_work_{__import__('os').getenv('USER', 'default')}.db")  # local working copy (always writable)

# Cached after first check
_use_local: bool | None = None


def _active_db() -> Path:
    """Return the DB path to use (local copy if virtiofs, canonical otherwise)."""
    global _use_local
    if _use_local is None:
        try:
            c = sqlite3.connect(str(DB_PATH), timeout=2)
            # Test with a real write: virtiofs allows reads but blocks SQLite locking
            c.execute("CREATE TABLE IF NOT EXISTS _write_test (x INTEGER)")
            c.execute("DROP TABLE IF EXISTS _write_test")
            c.commit()
            c.close()
            _use_local = False
        except sqlite3.OperationalError:
            _use_local = True

    if _use_local:
        # Sync from canonical if local copy is stale or missing
        if (not _WORK_DB.exists()
                or (DB_PATH.exists()
                    and DB_PATH.stat().st_mtime > _WORK_DB.stat().st_mtime)):
            shutil.copy2(str(DB_PATH), str(_WORK_DB))
        return _WORK_DB

    return DB_PATH


def sync_db():
    """
    Write the local working copy back to the canonical DB_PATH.
    Must be called after bulk write operations when running on virtiofs.
    No-op if the canonical DB is directly writable.
    """
    if _use_local and _WORK_DB.exists():
        with open(str(_WORK_DB), "rb") as src:
            data = src.read()
        with open(str(DB_PATH), "wb") as dst:
            dst.write(data)


def get_connection():
    conn = sqlite3.connect(str(_active_db()))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # ── Parliament Sessions ───────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,
            session_name    TEXT    NOT NULL,
            session_type    TEXT    NOT NULL,
            start_date      TEXT    NOT NULL,
            end_date        TEXT,
            total_sittings  INTEGER,
            notes           TEXT,
            UNIQUE(lok_sabha_no, session_no)
        )
    """)

    # ── Sitting Dates ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sitting_dates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,
            sitting_date    TEXT    NOT NULL,
            sitting_number  INTEGER,
            has_debate_pdf  INTEGER NOT NULL DEFAULT 0,
            source_pdf_id   INTEGER REFERENCES source_pdfs(id),
            notes           TEXT,
            UNIQUE(sitting_date, lok_sabha_no, session_no)
        )
    """)

    # ── Source PDFs ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS source_pdfs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,
            sitting_date    TEXT    NOT NULL,
            pdf_type        TEXT    NOT NULL,
            filename_type   TEXT    NOT NULL DEFAULT 'UCD',
            language        TEXT    NOT NULL DEFAULT 'english',
            url             TEXT    NOT NULL UNIQUE,
            filename        TEXT    NOT NULL,
            doc_id          INTEGER,
            downloaded_at   TEXT,
            parse_status    TEXT    DEFAULT 'pending'
        )
    """)

    # ── Members of Parliament ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            party           TEXT,
            constituency    TEXT,
            house           TEXT DEFAULT 'lok_sabha',
            UNIQUE(name_normalized, house)
        )
    """)

    # ── Core fact table ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS statements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,

            -- WHO
            member_id       INTEGER REFERENCES members(id),
            speaker_raw     TEXT NOT NULL,

            -- WHEN
            sitting_date    TEXT NOT NULL,
            lok_sabha_no    INTEGER NOT NULL,
            session_no      INTEGER NOT NULL,

            -- WHAT
            statement_type  TEXT NOT NULL,
            topic           TEXT,
            statement_text  TEXT NOT NULL,

            -- TRANSLATION
            original_text   TEXT,           -- set if statement_text is a translation
            original_language TEXT,         -- 'hi', 'bn', 'te', etc. — null if original English

            -- WHERE IN SOURCE
            source_pdf_id   INTEGER REFERENCES source_pdfs(id),
            page_number     INTEGER,
            char_offset     INTEGER,

            -- METADATA
            language        TEXT DEFAULT 'english',
            word_count      INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Digests (Claude-generated daily summaries) ────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS digests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sitting_date    TEXT    NOT NULL UNIQUE,
            digest_text     TEXT    NOT NULL,   -- markdown
            hot_topics      TEXT,               -- JSON array of topic strings
            created_at      TEXT    DEFAULT (datetime('now')),
            model_used      TEXT    DEFAULT 'claude-sonnet-4-6'
        )
    """)

    # ── Catalog — every item discovered from eparlib browse pages ────────────
    # debate_type: DSpace metadata field — e.g. "BUDGET (GENERAL)", "CALLING ATTENTION
    #   (RULE-197)", "NO-CONFIDENCE MOTION", "PRESIDENTIAL ADDRESS". Populated during
    #   the --resolve phase by reading the item detail page.
    # lok_sabha_no / session_no: parsed from item metadata during --resolve.
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalog (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id            INTEGER NOT NULL UNIQUE,
            collection_handle TEXT    NOT NULL,
            collection_name   TEXT    NOT NULL,
            item_date         TEXT,               -- ISO YYYY-MM-DD
            item_date_raw     TEXT,               -- original from site e.g. "6-Feb-2026"
            title             TEXT,
            language          TEXT,               -- 'english', 'hindi', 'original'
            debate_type       TEXT,               -- DSpace debate type metadata field
            lok_sabha_no      INTEGER,            -- from item metadata
            session_no        INTEGER,            -- from item metadata (as integer)
            session_no_raw    TEXT,               -- raw from site e.g. "VII"
            filename          TEXT,               -- resolved from item detail page
            bitstream_url     TEXT,               -- full download URL
            file_size_kb      INTEGER,
            downloaded        INTEGER NOT NULL DEFAULT 0,
            local_path        TEXT,
            discovered_at     TEXT    DEFAULT (datetime('now')),
            downloaded_at     TEXT
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_date         ON catalog(item_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_collection   ON catalog(collection_handle)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_downloaded   ON catalog(downloaded)")

    # ── Full-text search (FTS5) ───────────────────────────────────────────────
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

    _migrate_db()
    _seed_sessions()


def _migrate_db():
    """
    Add new columns / tables to an existing DB without losing data.
    Safe to run on any DB version — uses IF NOT EXISTS + try/except.
    """
    conn = get_connection()
    c    = conn.cursor()

    # ── statements table — new columns for translation support ────────────────
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(statements)")}

    if "original_text" not in existing_cols:
        c.execute("ALTER TABLE statements ADD COLUMN original_text TEXT")
        print("  ↳ Migration: added statements.original_text")

    if "original_language" not in existing_cols:
        c.execute("ALTER TABLE statements ADD COLUMN original_language TEXT")
        print("  ↳ Migration: added statements.original_language")

    # ── catalog table — eparlib item index ───────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS catalog (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id            INTEGER NOT NULL UNIQUE,
            collection_handle TEXT    NOT NULL,
            collection_name   TEXT    NOT NULL,
            item_date         TEXT,
            item_date_raw     TEXT,
            title             TEXT,
            language          TEXT,
            debate_type       TEXT,
            lok_sabha_no      INTEGER,
            session_no        INTEGER,
            session_no_raw    TEXT,
            filename          TEXT,
            bitstream_url     TEXT,
            file_size_kb      INTEGER,
            downloaded        INTEGER NOT NULL DEFAULT 0,
            local_path        TEXT,
            discovered_at     TEXT    DEFAULT (datetime('now')),
            downloaded_at     TEXT
        )
    """)
    # Migrate existing catalog rows (add new columns if missing)
    existing_catalog_cols = {row[1] for row in c.execute("PRAGMA table_info(catalog)")}
    for col, defn in [
        ("debate_type",   "TEXT"),
        ("lok_sabha_no",  "INTEGER"),
        ("session_no",    "INTEGER"),
        ("session_no_raw","TEXT"),
    ]:
        if col not in existing_catalog_cols:
            c.execute(f"ALTER TABLE catalog ADD COLUMN {col} {defn}")
            print(f"  ↳ Migration: added catalog.{col}")
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_date       ON catalog(item_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_collection ON catalog(collection_handle)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_downloaded ON catalog(downloaded)")

    # ── digests table — Claude-generated daily summaries ─────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS digests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sitting_date TEXT   NOT NULL UNIQUE,
            digest_text  TEXT   NOT NULL,
            hot_topics   TEXT,
            created_at   TEXT   DEFAULT (datetime('now')),
            model_used   TEXT   DEFAULT 'claude-sonnet-4-6'
        )
    """)

    conn.commit()
    conn.close()


def _seed_sessions():
    """Populate sessions and sitting_dates tables from sessions_data.py."""
    import sys
    sys.path.insert(0, str(_ROOT))
    from core.sessions_data import ALL_SESSIONS

    conn = get_connection()
    c = conn.cursor()
    sessions_added = 0
    dates_added = 0

    for session in ALL_SESSIONS:
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
            session["lok_sabha_no"], session["session_no"],
            session["session_name"], session["session_type"],
            session["start_date"], session.get("end_date"),
            session.get("total_sittings"), session.get("notes"),
        ))

        c.execute("""
            SELECT id FROM sessions WHERE lok_sabha_no = ? AND session_no = ?
        """, (session["lok_sabha_no"], session["session_no"]))
        session_id = c.fetchone()["id"]
        sessions_added += 1

        for i, date_str in enumerate(session["sitting_dates"], start=1):
            c.execute("""
                INSERT INTO sitting_dates
                    (session_id, lok_sabha_no, session_no, sitting_date, sitting_number)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sitting_date, lok_sabha_no, session_no) DO NOTHING
            """, (session_id, session["lok_sabha_no"], session["session_no"], date_str, i))
            if c.rowcount:
                dates_added += 1

    conn.commit()
    conn.close()
    print(f"✓ Sessions seeded: {sessions_added} sessions, {dates_added} new sitting dates")


def get_sitting_dates_summary():
    """Print a quick summary of sitting dates and their download status."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT
            s.session_name, s.session_type,
            COUNT(sd.id)               AS total_dates,
            SUM(sd.has_debate_pdf)     AS downloaded,
            COUNT(sd.id) - SUM(sd.has_debate_pdf) AS pending
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
