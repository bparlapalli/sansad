"""
core/record_schema.py — the Record: sourced entities, dated attributes, story nodes and edges.

Concept: docs/STORY_ENGINE.md (three layers: Story / Map / Record) and
docs/HYDERABAD_WEDGE.md §8 (entity templates). Called from core/db.py::_migrate_db,
so every existing sansad.db picks the tables up on the next init_db().

Design rules baked into the schema:
  - Sources are registered once (rec_sources) with publisher, dates and access notes.
    `independence_key` groups re-reports of one story / one publisher so the grader
    counts them once.
  - Entity attributes are append-only history (rec_entity_attrs): a changed role,
    party, project status or GO status is a NEW row with valid_from/valid_to, never
    an UPDATE of the old value.
  - A node gets an evidence grade ONLY from the verifier pass (record/verify.py),
    which must locate the exact passage (rec_node_sources.span_text) in the fetched
    source text. Until then evidence_grade is NULL = unverified.
  - Roles and weights are proposals by the agent (role_status/weight_status =
    'proposed') until the founder confirms them.
  - Every entity is private until the founder publishes (publish_state).
"""

RECORD_DDL = [
    # ── Sources — one row per document used ──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rec_sources (
        id               TEXT PRIMARY KEY,          -- slug, e.g. 'go-ms-69-2022'
        url              TEXT NOT NULL,
        title            TEXT,
        publisher        TEXT,                      -- 'Govt of Telangana, MA&UD', 'The Hindu'
        independence_key TEXT,                      -- same key = not independent (one outlet / one wire story)
        source_kind      TEXT NOT NULL,             -- primary | court | official_statement | news | research | dataset | listing | blog | party_statement | reference
        published_date   TEXT,                      -- ISO date if known
        retrieved_at     TEXT,                      -- when WE last fetched it (NULL = never fetched)
        discovered_via   TEXT,                      -- 'web_search', 'manual', 'sansad.db'
        access           TEXT NOT NULL DEFAULT 'unchecked',  -- unchecked | open | blocked_env | blocked_site | captcha | login | paywall | not_found
        access_notes     TEXT,
        terms_notes      TEXT,
        local_path       TEXT,                      -- cached text under data/, if fetched
        content_sha256   TEXT,
        added_at         TEXT DEFAULT (datetime('now'))
    )
    """,
    # ── Entities — one row per area / policy / project / org / person / event / quote
    """
    CREATE TABLE IF NOT EXISTS rec_entities (
        id             TEXT PRIMARY KEY,            -- slug, e.g. 'kokapet', 'go-111'
        type           TEXT NOT NULL,               -- area | policy | infra | org | person | event | quote | place
        name           TEXT NOT NULL,
        aliases        TEXT,                        -- JSON list
        summary        TEXT,
        publish_state  TEXT NOT NULL DEFAULT 'private',  -- private | approved | public
        people_id      INTEGER REFERENCES people(id),    -- link to party registry, if the person is tracked there
        member_id      INTEGER REFERENCES members(id),   -- link to Parliament record, if an MP
        added_at       TEXT DEFAULT (datetime('now'))
    )
    """,
    # ── Dated attributes — history, never overwritten ─────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rec_entity_attrs (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id      TEXT NOT NULL REFERENCES rec_entities(id),
        attr           TEXT NOT NULL,               -- 'role', 'party', 'status', 'go_number', 'zone', 'lat', …
        value          TEXT NOT NULL,
        valid_from     TEXT,                        -- NULL = since before we track
        valid_to       TEXT,                        -- NULL = still current (as far as we know)
        date_precision TEXT DEFAULT 'day',          -- day | month | year | approx
        source_id      TEXT REFERENCES rec_sources(id),
        span_text      TEXT,                        -- passage that supports it
        span_is_verbatim INTEGER NOT NULL DEFAULT 0,
        span_status    TEXT NOT NULL DEFAULT 'unlocated',  -- unlocated | located | not_found | source_unreachable
        evidence_grade TEXT,                        -- confirmed | reported | claimed | NULL (unverified)
        recorded_at    TEXT DEFAULT (datetime('now')),
        UNIQUE(entity_id, attr, value, valid_from, source_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rec_attrs_entity ON rec_entity_attrs(entity_id, attr)",
    # ── Stories — a post / report that cites nodes ────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rec_stories (
        id          TEXT PRIMARY KEY,               -- 'hyd-post-1'
        title       TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'draft',  -- draft | review | published (founder only)
        created_at  TEXT DEFAULT (datetime('now'))
    )
    """,
    # ── Nodes — one decision or event on a Map ────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rec_nodes (
        id                    TEXT PRIMARY KEY,
        date                  TEXT,                 -- ISO, truncated to precision
        date_precision        TEXT NOT NULL DEFAULT 'day',  -- day | month | year | approx
        actor_id              TEXT REFERENCES rec_entities(id),
        action                TEXT NOT NULL,        -- verb phrase: 'issued G.O.Ms.No.69 rescinding GO 111'
        decision_text         TEXT,                 -- fuller neutral description
        role                  TEXT,                 -- deliberate_bet | spillover | unblocker | roadblock | wildcard
        role_status           TEXT NOT NULL DEFAULT 'proposed',   -- proposed | confirmed (founder)
        weight                TEXT,                 -- essential | accelerant | minor
        weight_status         TEXT NOT NULL DEFAULT 'proposed',
        intent_toward_outcome INTEGER,              -- 1 = aimed at this outcome
        evidence_grade        TEXT,                 -- set ONLY by record/verify.py; NULL = unverified
        verified_at           TEXT,
        counterfactual_note   TEXT,
        comparison_case       TEXT,
        layer                 TEXT NOT NULL DEFAULT 'fact',  -- fact | claim  (hypotheses never enter the Record)
        claimant_id           TEXT REFERENCES rec_entities(id),  -- for layer='claim'
        added_at              TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rec_story_nodes (
        story_id  TEXT NOT NULL REFERENCES rec_stories(id),
        node_id   TEXT NOT NULL REFERENCES rec_nodes(id),
        section   TEXT,                             -- 'boomed' | 'risk' | 'next' | 'who'
        PRIMARY KEY (story_id, node_id)
    )
    """,
    # Places / subjects / other entities a node touches (actor is on the node itself).
    """
    CREATE TABLE IF NOT EXISTS rec_node_entities (
        node_id   TEXT NOT NULL REFERENCES rec_nodes(id),
        entity_id TEXT NOT NULL REFERENCES rec_entities(id),
        relation  TEXT NOT NULL DEFAULT 'about',    -- place | subject | about | affected
        PRIMARY KEY (node_id, entity_id, relation)
    )
    """,
    # Evidence: which passage in which source supports the node.
    """
    CREATE TABLE IF NOT EXISTS rec_node_sources (
        node_id       TEXT NOT NULL REFERENCES rec_nodes(id),
        source_id     TEXT NOT NULL REFERENCES rec_sources(id),
        span_text     TEXT,                         -- passage the extractor expects to find (verbatim if known)
        span_is_verbatim INTEGER NOT NULL DEFAULT 0,  -- 0 = paraphrase from a search summary
        span_status   TEXT NOT NULL DEFAULT 'unlocated',  -- unlocated | located | not_found | source_unreachable
        span_offset   INTEGER,                      -- char offset in the cached text, once located
        verifier_note TEXT,
        checked_at    TEXT,
        PRIMARY KEY (node_id, source_id)
    )
    """,
    # ── Edges — directed graph between nodes ──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rec_edges (
        from_node      TEXT NOT NULL REFERENCES rec_nodes(id),
        to_node        TEXT NOT NULL REFERENCES rec_nodes(id),
        relation       TEXT NOT NULL,               -- enabled | accelerated | blocked | triggered
        status         TEXT NOT NULL DEFAULT 'proposed',
        evidence_grade TEXT,
        note           TEXT,
        PRIMARY KEY (from_node, to_node, relation)
    )
    """,
]


def create_record_tables(conn) -> None:
    """Create the Record tables on an open sqlite3 connection (idempotent)."""
    for stmt in RECORD_DDL:
        conn.execute(stmt)
    conn.commit()
