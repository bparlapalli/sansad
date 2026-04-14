# ParamaSrota — UI v2 Design Spec

> This document outlines the planned redesign of the web application into three interconnected surfaces: a **Wiki**, a **News feed**, and a **Forum**.

---

## Guiding principle

The current app is a **viewer** — you browse parsed data. v2 should feel like a **living intelligence layer** on top of Parliament: every piece of information connects to everything else, new data automatically generates context-rich news, and users can interrogate the data conversationally.

---

## 1. Wiki — `/wiki/`

A Wikipedia-style knowledge graph where every entity (person, topic, bill, event, place) has its own page, and every claim on that page links back to the exact Lok Sabha statement that supports it.

### Entity types

| Type | URL | Examples |
|------|-----|---------|
| Person (MP) | `/wiki/person/{slug}` | rahul-gandhi, narendra-modi |
| Topic | `/wiki/topic/{slug}` | budget-2025, farmers-protest, gst |
| Bill | `/wiki/bill/{slug}` | waqf-amendment-bill, jan-vishwas-bill |
| Event | `/wiki/event/{slug}` | presidential-address-2024, no-confidence-2024 |
| Ministry | `/wiki/ministry/{slug}` | finance-ministry, defence-ministry |
| Constituency | `/wiki/constituency/{slug}` | wayanad, varanasi |

### Person page — `/wiki/person/{slug}`

```
┌─────────────────────────────────────────────────────────┐
│  RAHUL GANDHI                          [INC] [Wayanad]  │
│  Member of Parliament, 18th Lok Sabha                   │
├─────────────┬───────────────────────────────────────────┤
│  POSITIONS  │  KEY QUOTES                                │
│  taken on   │  "The government must answer..."           │
│  key topics │  [Mar 19 2025] on Budget                   │
├─────────────┴───────────────────────────────────────────┤
│  ACTIVITY TIMELINE                                       │
│  ▓▓░░▓▓▓░░▓▓  (spark line across sessions)             │
├─────────────────────────────────────────────────────────┤
│  ALL STATEMENTS  (filterable by topic, date, type)      │
│  [Speech] [Question] [Interruption] chips               │
│  Each statement → source PDF page link                  │
├─────────────────────────────────────────────────────────┤
│  RELATED ENTITIES                                        │
│  Topics they discuss most · Bills they spoke on ·       │
│  MPs they quote / respond to                            │
└─────────────────────────────────────────────────────────┘
```

### Topic page — `/wiki/topic/{slug}`

```
┌─────────────────────────────────────────────────────────┐
│  TOPIC: FARMERS' MSP                                     │
│  Discussed across 3 sessions · 47 speakers · 218 stmts  │
├─────────────────────────────────────────────────────────┤
│  TIMELINE  [Session 4] [Session 6] [Session 7]          │
│  ── Feb 2026 ──── Dec 2025 ──── Mar 2025 ──────         │
├─────────────────────────────────────────────────────────┤
│  KEY POSITIONS                                           │
│  Government: "MSP has increased by 50%..."              │
│  Opposition: "Swaminathan formula not implemented..."   │
├─────────────────────────────────────────────────────────┤
│  TOP SPEAKERS on this topic                              │
│  Related topics: Agriculture · Budget · Subsidies       │
└─────────────────────────────────────────────────────────┘
```

### DB additions needed

```sql
-- Entities discovered by Claude at parse time
CREATE TABLE entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,   -- 'person', 'topic', 'bill', 'event', 'ministry'
    display_name TEXT NOT NULL,
    description TEXT,            -- Claude-generated one-liner
    first_seen  TEXT,            -- earliest sitting_date where mentioned
    last_seen   TEXT,
    mention_count INTEGER DEFAULT 0
);

-- Many-to-many: statements ↔ entities
CREATE TABLE entity_mentions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id INTEGER NOT NULL REFERENCES statements(id),
    entity_id    INTEGER NOT NULL REFERENCES entities(id),
    role         TEXT,           -- 'subject', 'object', 'mentioned', 'quoted'
    confidence   REAL,           -- 0.0–1.0
    UNIQUE(statement_id, entity_id)
);
```

Entity extraction happens in `pipeline.py` after parsing each PDF. Claude reads all statements from a sitting and returns a structured list of entities + mentions. Batched to keep costs low (one Claude call per PDF, not per statement).

---

## 2. News — `/` (home page redesign)

Instead of: parse PDF → store statements → run Claude later to make a gist

New flow: parse PDF → **Claude runs during pipeline** → stores a full news article with historical context already embedded.

### The new parse pipeline

```
PDF downloaded
    ↓
pdf_parser.py — extract statements
    ↓
translator.py — translate Hindi → English (Sarvam)
    ↓
entity_extractor.py (NEW) — Claude extracts entities, mentions
    ↓
news_writer.py (NEW) — Claude writes today's article:
    - Queries past statements (FTS5) for context on each story
    - Writes article with "previously on..." paragraphs baked in
    - Stores in news_articles table
    ↓
All stored together in one transaction
```

### News article structure

```
┌─────────────────────────────────────────────────────────┐
│  Parliament Today — March 19, 2025                      │
│  Budget Session 2025 · Sitting 23                       │
├─────────────────────────────────────────────────────────┤
│  🔴 LIVE  Finance Minister Presents Railway Budget      │
│                                                         │
│  [Claude-written article with full context]             │
│  "Today Nirmala Sitharaman announced ₹2.5L Cr for      │
│   railways — the largest allocation since 2019 when    │  │   Piyush Goyal had proposed..."                        │
│                                                         │
│  ┌────────────────────────────────────────────────┐    │
│  │ 🔗 In context: How this connects to past       │    │
│  │    debates on infrastructure spending           │    │
│  └────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  ALSO TODAY                                             │
│  · Opposition raises Adani issue — 3rd time this       │
│    session [see previous: Dec 2024, Jul 2024]          │
│  · Question Hour: 14 starred questions answered        │
├─────────────────────────────────────────────────────────┤
│  ARCHIVE — previous sittings                            │
│  [Mar 18] [Mar 17] [Mar 15] ...                        │
└─────────────────────────────────────────────────────────┘
```

### DB additions needed

```sql
CREATE TABLE news_articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sitting_date TEXT NOT NULL UNIQUE,
    headline     TEXT NOT NULL,
    subheadline  TEXT,
    body_md      TEXT NOT NULL,      -- full markdown article
    stories_json TEXT,               -- JSON array of {title, summary, entity_ids}
    related_past TEXT,               -- JSON array of {date, summary, link}
    model_used   TEXT DEFAULT 'claude-sonnet-4-6',
    created_at   TEXT DEFAULT (datetime('now'))
);

-- Link articles to entities
CREATE TABLE article_entities (
    article_id INTEGER REFERENCES news_articles(id),
    entity_id  INTEGER REFERENCES entities(id),
    role       TEXT,    -- 'subject', 'mentioned'
    PRIMARY KEY (article_id, entity_id)
);
```

### New module: `parser/news_writer.py`

```python
def write_news_article(sitting_date, statements, db_conn) -> dict:
    """
    Given today's parsed statements, query past context and write a news article.
    Returns {headline, subheadline, body_md, stories_json, related_past}.
    
    Steps:
    1. Cluster statements into 3–5 stories (by topic/entity)
    2. For each story, FTS5 search past statements for context
    3. Single Claude call: "You are a parliamentary correspondent. Write today's
       article with this context baked in. Format: headline + body paragraphs."
    4. Return structured JSON for storage
    """
```

---

## 3. Forum — `/discuss/`

Each news article and wiki page has a threaded discussion section. Users can ask questions backed by the actual scraped data.

### Two modes

**Free discussion** — regular threaded comments on a news article or wiki page.

**Research thread** — user asks a question in natural language, the system finds relevant Parliament statements and surfaces them as evidence. Community then annotates/discusses.

```
┌─────────────────────────────────────────────────────────┐
│  💬 Discussion — Budget 2025 · 12 posts                 │
├─────────────────────────────────────────────────────────┤
│  🔍 Research question:                                   │
│  ┌──────────────────────────────────────────────┐      │
│  │ "When did the opposition last accept a        │      │
│  │  budget speech without walkout?"              │      │
│  └──────────────────────────────────────────────┘      │
│  [Search Parliament Records]                            │
│                                                         │
│  ↳ Found 3 relevant statements:                        │
│    [Jul 2022] Adhir Ranjan: "We accept the budget..."  │
│    [Feb 2020] ...                                      │
│    [View all 3 →]                                      │
├─────────────────────────────────────────────────────────┤
│  USER POSTS                                             │
│  Bharath · 2h ago                                       │
│  "The railway allocation looks similar to 2019..."     │
│  [Reply] [Quote statement] [👍 3]                      │
└─────────────────────────────────────────────────────────┘
```

### DB additions needed

```sql
CREATE TABLE discussions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    context_type TEXT NOT NULL,   -- 'news_article', 'wiki_entity', 'sitting_date'
    context_id   TEXT NOT NULL,   -- article id or entity slug or date
    title        TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    post_count   INTEGER DEFAULT 0,
    UNIQUE(context_type, context_id)
);

CREATE TABLE posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    discussion_id   INTEGER NOT NULL REFERENCES discussions(id),
    parent_id       INTEGER REFERENCES posts(id),   -- for threading
    author_name     TEXT NOT NULL DEFAULT 'Anonymous',
    body_md         TEXT NOT NULL,
    -- Research mode
    query_text      TEXT,              -- if this is a research question
    result_stmts    TEXT,              -- JSON array of statement IDs found
    upvotes         INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);
```

### The research query endpoint

`POST /api/research` — takes `{query, context_type, context_id}`, returns relevant statements.

Implementation v1: FTS5 search over statements + speaker/topic filters.
Implementation v2: vector embeddings (sqlite-vec or pgvector) for semantic search.

---

## Technical architecture changes

### New modules to build

| Module | Purpose |
|--------|---------|
| `parser/entity_extractor.py` | Claude call → extract entities + mentions from a sitting's statements |
| `parser/news_writer.py` | Claude call → write context-rich news article at parse time |
| `app/wiki.py` | Flask Blueprint `/wiki` — entity pages |
| `app/news.py` | Flask Blueprint `/` — redesigned home + article view |
| `app/forum.py` | Flask Blueprint `/discuss` — discussion + research threads |

### Build order

1. **entities + entity_mentions tables** (DB migration in `core/db.py`)
2. **entity_extractor.py** — entity extraction at parse time
3. **wiki.py** — person + topic pages (can build with existing statement data)
4. **news_writer.py** — Claude at parse time
5. **news.py** — redesigned home page
6. **forum.py** — discussion + research

### What stays the same

- `core/db.py` schema (extended, not replaced)
- `scrapers/parliament/playwright_scraper.py` — no changes
- `parser/pdf_parser.py` + `translator.py` — no changes
- `app/admin.py` — no changes
- All existing routes (`/search`, `/speakers`, `/sessions`, `/stats`) — kept as-is

---

## Design language

Admin uses sans-serif (Inter/Segoe UI). The public-facing site should feel like a quality newspaper — Georgia serif for reading, clean navigation, mobile-friendly.

- Primary: `#0f2818` (deep green)
- Accent: `#2a6a3a`
- Background: `#f8f7f2` (warm off-white)
- Wiki page accent: `#1a3a7e` (link blue, distinct from green nav)
- Forum accent: `#7a2a1a` (warm red-brown for discussion)

---

## GitHub Issues

- #42 — Admin UI (✅ done)
- #43 — Wiki blueprint (to open)
- #44 — News v2 pipeline (to open)
- #45 — Forum + research threads (to open)
