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

import os
import platform
import shutil
import sqlite3
import tempfile
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT    = Path(__file__).resolve().parent.parent
# SANSAD_DB_PATH overrides the DB location — used in production (Render) to
# point at a small, ingested public.db instead of the full local sansad.db.
DB_PATH  = Path(os.getenv("SANSAD_DB_PATH", str(_ROOT / "sansad.db")))
_username = os.getenv("USERNAME") or os.getenv("USER") or "default"
_WORK_DB = Path(tempfile.gettempdir()) / f"sansad_work_{_username}.db"

# Cached after first check
_use_local: bool | None = None


def _active_db() -> Path:
    """Return the DB path to use (local copy if virtiofs, canonical otherwise).

    On Windows the project folder is a real local filesystem — always use DB_PATH
    directly.  On Linux/macOS the folder may be virtiofs-mounted (Cowork sandbox),
    in which case SQLite file-locking fails; we copy the DB to /tmp and work there.
    """
    global _use_local
    if _use_local is None:
        # Windows: local files are always writable — skip virtiofs detection
        if platform.system() == "Windows":
            _use_local = False
        else:
            try:
                c = sqlite3.connect(str(DB_PATH), timeout=2)
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

    # ── Statement chunks — paragraph-sized slices of a statement for search ───
    # A single statement (one speaker turn) can run to a full speech covering
    # several subjects. Chunks give search a unit small enough that the match
    # is visible in the snippet, while statement_id still links back to the
    # full text and its speaker/date/page context.
    c.execute("""
        CREATE TABLE IF NOT EXISTS statement_chunks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id    INTEGER NOT NULL REFERENCES statements(id),
            chunk_index     INTEGER NOT NULL,
            chunk_text      TEXT    NOT NULL,
            word_count      INTEGER,
            UNIQUE(statement_id, chunk_index)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_statement ON statement_chunks(statement_id)")

    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(
            chunk_text,
            content='statement_chunks',
            content_rowid='id'
        )
    """)

    c.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai
        AFTER INSERT ON statement_chunks BEGIN
            INSERT INTO chunks_fts(rowid, chunk_text)
            VALUES (new.id, new.chunk_text);
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad
        AFTER DELETE ON statement_chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text)
            VALUES ('delete', old.id, old.chunk_text);
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

    # ── Politician profiles — Claude-generated MP bios ────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS politician_profiles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id    INTEGER NOT NULL UNIQUE REFERENCES members(id),
            profile_text TEXT    NOT NULL,
            key_topics   TEXT,
            generated_at TEXT    DEFAULT (datetime('now')),
            model_used   TEXT    DEFAULT 'claude-sonnet-4-6'
        )
    """)

    # ── Member history — party / constituency changes over time ───────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS member_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id      INTEGER NOT NULL REFERENCES members(id),
            attribute      TEXT    NOT NULL,
            old_value      TEXT,
            new_value      TEXT    NOT NULL,
            effective_date TEXT,
            source         TEXT    DEFAULT 'manual',
            notes          TEXT,
            created_at     TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ── PIB press releases — second data source (scrapers/pib/pib_scraper.py) ─
    # One row per release, keyed by PIB's own release ID (PRID). Rows are
    # inserted as 'listed' from the daily listing page, then filled in
    # (body_text etc.) and flipped to 'fetched' once the release page is read.
    c.execute("""
        CREATE TABLE IF NOT EXISTS pib_releases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            prid            INTEGER NOT NULL UNIQUE,
            title           TEXT    NOT NULL,
            ministry        TEXT,
            release_date    TEXT,               -- ISO YYYY-MM-DD
            posted_at       TEXT,               -- ISO YYYY-MM-DD HH:MM
            region          TEXT,               -- e.g. 'PIB Delhi'
            language        TEXT    NOT NULL DEFAULT 'english',
            body_text       TEXT,
            word_count      INTEGER,
            url             TEXT    NOT NULL,
            translations    TEXT,               -- JSON {language: prid}
            fetch_status    TEXT    NOT NULL DEFAULT 'listed',  -- listed | fetched | error
            fetch_error     TEXT,
            discovered_at   TEXT    DEFAULT (datetime('now')),
            fetched_at      TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_pib_date     ON pib_releases(release_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pib_ministry ON pib_releases(ministry)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pib_status   ON pib_releases(fetch_status)")

    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS pib_releases_fts
        USING fts5(
            title,
            ministry,
            body_text,
            content='pib_releases',
            content_rowid='id'
        )
    """)
    # Rows are updated after insert (listed → fetched), so the index needs
    # insert, delete and update triggers to stay in sync.
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS pib_releases_ai
        AFTER INSERT ON pib_releases BEGIN
            INSERT INTO pib_releases_fts(rowid, title, ministry, body_text)
            VALUES (new.id, new.title, new.ministry, new.body_text);
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS pib_releases_ad
        AFTER DELETE ON pib_releases BEGIN
            INSERT INTO pib_releases_fts(pib_releases_fts, rowid, title, ministry, body_text)
            VALUES ('delete', old.id, old.title, old.ministry, old.body_text);
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS pib_releases_au
        AFTER UPDATE ON pib_releases BEGIN
            INSERT INTO pib_releases_fts(pib_releases_fts, rowid, title, ministry, body_text)
            VALUES ('delete', old.id, old.title, old.ministry, old.body_text);
            INSERT INTO pib_releases_fts(rowid, title, ministry, body_text)
            VALUES (new.id, new.title, new.ministry, new.body_text);
        END
    """)

    # ── Parties, people & their accounts — off-floor sources (YouTube, X, sites) ─
    # Seeded from core/party_registry.py. A person's party is never stored on
    # the person: it lives in time-bounded `affiliations` rows, so a leader who
    # switches parties keeps one identity and every quote is tagged with the
    # party they were in *on the day they said it* (media_items.party_id).
    c.execute("""
        CREATE TABLE IF NOT EXISTS parties (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT    NOT NULL UNIQUE,     -- 'inc', 'bjp', 'cjp'
            name        TEXT    NOT NULL,
            short_name  TEXT,
            kind        TEXT    NOT NULL DEFAULT 'party',   -- party | movement
            notes       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT    NOT NULL UNIQUE,     -- 'rahul-gandhi'
            name        TEXT    NOT NULL,
            aliases     TEXT,                        -- JSON list, matched against video titles
            member_id   INTEGER REFERENCES members(id),  -- link to Parliament record, if an MP
            notes       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS affiliations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id   INTEGER NOT NULL REFERENCES people(id),
            party_id    INTEGER NOT NULL REFERENCES parties(id),
            role        TEXT,
            start_date  TEXT,                        -- NULL = since before we track
            end_date    TEXT,                        -- NULL = current
            source      TEXT,
            UNIQUE(person_id, party_id, start_date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS source_accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT    NOT NULL,        -- youtube | x | website
            kind            TEXT    NOT NULL DEFAULT 'channel',  -- channel | search
            handle          TEXT    NOT NULL,        -- '@bjp', or the query for kind=search
            external_id     TEXT,                    -- YouTube channel id etc.
            url             TEXT,
            owner_party_id  INTEGER REFERENCES parties(id),
            owner_person_id INTEGER REFERENCES people(id),
            verified        INTEGER NOT NULL DEFAULT 0,  -- 1 = confirmed official
            active          INTEGER NOT NULL DEFAULT 1,
            notes           TEXT,
            UNIQUE(platform, handle)
        )
    """)
    # One row per video / post / release. Platform-agnostic so X and party
    # websites can land in the same table later.
    c.execute("""
        CREATE TABLE IF NOT EXISTS media_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT    NOT NULL,
            external_id     TEXT    NOT NULL,        -- YouTube video id
            account_id      INTEGER REFERENCES source_accounts(id),
            title           TEXT    NOT NULL,
            description     TEXT,
            url             TEXT    NOT NULL,
            published_at    TEXT,                    -- ISO YYYY-MM-DD HH:MM (UTC)
            published_date  TEXT,                    -- ISO YYYY-MM-DD
            duration_sec    INTEGER,
            content_kind    TEXT,                    -- press_conference | speech | interview | other
            person_id       INTEGER REFERENCES people(id),   -- who is speaking, if known
            party_id        INTEGER REFERENCES parties(id),  -- speaker's party ON published_date
            attribution     TEXT,                    -- owner | title_match | search | none
            fetch_status    TEXT    NOT NULL DEFAULT 'listed',  -- listed | fetched | no_transcript | error
            transcript_lang TEXT,
            transcript_auto INTEGER,                 -- 1 = auto-generated captions
            transcript_text TEXT,
            word_count      INTEGER,
            fetch_error     TEXT,
            discovered_at   TEXT    DEFAULT (datetime('now')),
            fetched_at      TEXT,
            UNIQUE(platform, external_id)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_date   ON media_items(published_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_person ON media_items(person_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_party  ON media_items(party_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_status ON media_items(fetch_status)")

    # ~60-word timed slices of a transcript — the "quote" unit, with the
    # second offset so each one deep-links to that moment in the video.
    c.execute("""
        CREATE TABLE IF NOT EXISTS media_chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id     INTEGER NOT NULL REFERENCES media_items(id),
            chunk_index INTEGER NOT NULL,
            start_sec   REAL,
            text        TEXT    NOT NULL,
            text_en     TEXT,                        -- filled by translation later
            UNIQUE(item_id, chunk_index)
        )
    """)
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS media_chunks_fts
        USING fts5(text, text_en, content='media_chunks', content_rowid='id')
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS media_chunks_ai
        AFTER INSERT ON media_chunks BEGIN
            INSERT INTO media_chunks_fts(rowid, text, text_en) VALUES (new.id, new.text, new.text_en);
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS media_chunks_ad
        AFTER DELETE ON media_chunks BEGIN
            INSERT INTO media_chunks_fts(media_chunks_fts, rowid, text, text_en)
            VALUES ('delete', old.id, old.text, old.text_en);
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS media_chunks_au
        AFTER UPDATE ON media_chunks BEGIN
            INSERT INTO media_chunks_fts(media_chunks_fts, rowid, text, text_en)
            VALUES ('delete', old.id, old.text, old.text_en);
            INSERT INTO media_chunks_fts(rowid, text, text_en) VALUES (new.id, new.text, new.text_en);
        END
    """)

    # ── The Record — sourced entities, dated attributes, story nodes, edges ──
    # Schema + rules live in core/record_schema.py (see docs/STORY_ENGINE.md).
    from core.record_schema import create_record_tables
    create_record_tables(conn)

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
