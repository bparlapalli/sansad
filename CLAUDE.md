# ParamaSrota — Parliament Intelligence

> *"परम श्रोता" — The Supreme Listener*

Read this file at the start of every session to get up to speed.

Scrapes Lok Sabha debate PDFs, parses attributed statements, translates Hindi/regional content to English, and presents everything as a linked wiki + live news feed with community discussion.

---

## Project structure (monorepo)

```
sansad/
├── core/                    # Shared: DB schema, sessions data
│   ├── db.py                # SQLite schema + seed. DB_PATH = root/sansad.db
│   └── sessions_data.py     # 18th LS sessions + sitting dates + doc_id anchors
│
├── scrapers/
│   └── parliament/          # eparlib.sansad.in PDF downloader
│       ├── scraper.py           # Legacy: probe-based doc_id guesser (keep for reference)
│       ├── playwright_scraper.py # Playwright browser scraper — catalog + download
│       ├── local_scan.py        # Register manually-dropped PDFs
│       └── main.py              # CLI entry point for legacy scraper only
│
├── parser/
│   ├── pdf_parser.py        # Text extraction + speaker attribution + language detection
│   ├── translator.py        # Sarvam AI (Hindi/regional → English)
│   ├── pipeline.py          # Orchestrates parse + translate + store
│   └── test_sarvam.py       # Quick Sarvam API connectivity test (run locally)
│
├── app/
│   ├── app.py               # Flask app (registers all blueprints)
│   ├── admin.py             # ✅ Admin blueprint — scraper control, catalog browser, parse trigger
│   ├── digest.py            # Claude API daily digest generator
│   ├── query.py             # Search functions (used by app + CLI)
│   └── templates/           # Jinja2 HTML templates
│       ├── base.html        # Shared masthead + nav (includes Admin link)
│       ├── home.html        # Today's digest + proceedings
│       ├── search.html      # FTS5 search with filters
│       ├── topic.html       # Topic deep-dive with timeline
│       └── speaker.html     # Speaker profile
│
├── main.py                  # Full pipeline entry point (scrape + parse + translate)
├── pdfs/                    # Downloaded PDF files
├── sansad.db                # SQLite database (do not commit)
└── requirements.txt
```

Every sub-package adds `_ROOT = Path(__file__).resolve().parent[.parent]` to `sys.path`,
so `from core.db import ...` works regardless of where you run from.

---

## How to run

```bash
# ── First time ────────────────────────────────────────────────────────────────
pip install -r requirements.txt
pip install playwright && playwright install chromium   # for Playwright scraper
python main.py --status          # init DB + show sitting date status

# ── Playwright scraper (preferred) ────────────────────────────────────────────
# Phase 1: Build catalog (scrapes browse pages, ~1 req per 20 items — FAST)
python scrapers/parliament/playwright_scraper.py --catalog
python scrapers/parliament/playwright_scraper.py --catalog --collections debates presidential budget

# Phase 2: Resolve filenames (visits item pages to get exact PDF filename)
python scrapers/parliament/playwright_scraper.py --resolve --limit 200

# Phase 3: Download PDFs
python scrapers/parliament/playwright_scraper.py --download --limit 30
python scrapers/parliament/playwright_scraper.py --download --from 2024-01-01

# Full pipeline in one command
python scrapers/parliament/playwright_scraper.py --catalog --resolve --download --collections debates --limit 20

# Catalog status
python scrapers/parliament/playwright_scraper.py --status

# All available collections:
#   debates         Lok Sabha Debates (Text) — 6,458 items
#   debates_en      Lok Sabha Debates (English only)
#   debates_hi      Lok Sabha Debates (Hindi only)
#   debates_ucd     Lok Sabha Debates (Uncorrected/UCD)
#   presidential    Presidential Addresses — 181 items
#   budget          Budget Speeches
#   committee       Parliamentary Committee Reports
#   pm_speeches     PM Speeches
#   resume          Resume of Work Done by Lok Sabha
#   bulletin1       Lok Sabha Bulletin I
#   bulletin2       Lok Sabha Bulletin II
#   questions_p1    Questions Part 1 (Q&A)
#   questions_p2    Questions Part 2 (Other)
#   historical      Historical Debates (1st–17th LS)
#   constituent     Constituent Assembly Debates

# ── Register manually dropped PDFs ────────────────────────────────────────────
python scrapers/parliament/local_scan.py        # scan pdfs/ dir + register
python scrapers/parliament/local_scan.py --list # list all registered PDFs

# ── Parse downloaded PDFs ──────────────────────────────────────────────────────
python main.py --parse-only                  # parse all registered PDFs
python main.py --parse-only --translate      # parse + Sarvam AI translation

# ── Test Sarvam AI key ────────────────────────────────────────────────────────
python parser/test_sarvam.py                 # quick connectivity + translation test

# ── Web app ────────────────────────────────────────────────────────────────────
python app/app.py                            # opens at http://localhost:5100
#   /          → home (latest news + digest)
#   /search    → FTS5 full-text search
#   /speakers  → all MPs
#   /sessions  → session overview
#   /admin/    → Admin UI (scraper control, catalog browser, parse trigger)

# ── CLI search ────────────────────────────────────────────────────────────────
python app/query.py --stats
python app/query.py --speaker "Rahul Gandhi"
python app/query.py --search "Vande Mataram"
```

---

## AI integrations

### Claude (app/digest.py)
- Set `ANTHROPIC_API_KEY` to enable AI-generated daily summaries
- Model: `claude-sonnet-4-6`
- Digests cached in `digests` table — regenerate with `python app/digest.py 2025-03-19 --force`
- **Future**: Claude to run AT parse time, not after — generating contextual news articles

### Sarvam AI (parser/translator.py)
- Key stored in `.env` as `SARVAM_API_KEY=sk_35fqajs8_...` (gitignored)
- API: `https://api.sarvam.ai/translate`, model `mayura:v1`
- Supports: hi, bn, te, mr, ta, gu, kn, ml, pa, or
- When key absent: pipeline stores Hindi text as-is
- Test: `python parser/test_sarvam.py` (needs network access — run on local machine)
- Enable per-run: `python main.py --parse-only --translate`
- **Known issue**: Hindi Devanagari PDFs (lsd files) extract 0 statements — pdf_parser.py
  needs a Hindi-aware extraction path before translation becomes useful

---

## Sessions in core/sessions_data.py

| # | Name | Type | Dates | Status |
|---|------|------|-------|--------|
| 1 | First Session | special | Jun 24 – Jul 3, 2024 | dates estimated |
| 2 | Budget Session Jul–Aug 2024 | budget | Jul 22 – Aug 9, 2024 | anchor: Aug 1 = 2981286 |
| 3 | Winter Session 2024 | winter | Nov 25 – Dec 20, 2024 | dates estimated |
| 4 | Budget Session 2025 | budget | Jan 31 – Apr 4, 2025 | confirmed; Mar 19 = 2989556, Apr 1 = 2990867 |
| 5 | Monsoon Session 2025 | monsoon | Jul 21 – Aug 22, 2025 | estimated only |
| 6 | Winter Session 2025 | winter | Nov 24 – Dec 19, 2025 | Dec 8 + Dec 19 confirmed |
| 7 | Budget Session 2026 | budget | Jan 31 – May 2026 | Jan 28–29 dates exist in DB but not seeded |

---

## PDFs currently downloaded / registered

| File | Session | Language | Notes |
|------|---------|----------|-------|
| `UCD_18_4_19-03-2025_Fullday.pdf` | 4 | English | Parsed OK — 50+ statements |
| `lsd_18_VI_08-12-2025.pdf` | 6 | Hindi | 1404 pages — needs Hindi parser fix |
| `lsd_18_VI_19-12-2025.pdf` | 6 | Hindi | 8 pages valedictory |
| `lsd_18_VII_28-01-2026_original_corrected.pdf` | 7 | Hindi | 89 pages |
| `lsd_18_VII_03-02-2026_original_corrected.pdf` | 7 | Hindi | Large |
| `lsd_18_VI_05-12-2025.pdf` | 6 | Hindi | 15MB — parse on local machine |

---

## eparlib.sansad.in site structure

DSpace instance. No REST API or OAI-PMH exposed.

| Collection name | Handle | Count | Notes |
|---|---|---|---|
| Lok Sabha Debates (Text) | 7 | 6,458 | All debates 1952–2026 |
| Lok Sabha Debates (English) | 2963706 | — | English subset |
| Lok Sabha Debates (Hindi) | 796090 | — | Hindi subset |
| Lok Sabha Debates (Uncorrected) | 2953354 | — | UCD files |
| Presidential Addresses | 14 | 181 | From 1950 onwards |
| Budget Speeches | 12 | — | General + Railway budgets |
| Parliamentary Committee Reports | 13 | — | All committees |
| PM Speeches | 800962 | — | |

Browse URL pattern: `https://eparlib.sansad.in/handle/123456789/{handle}?offset={N}`
Item URL: `https://eparlib.sansad.in/handle/123456789/{doc_id}`
Bitstream URL: `https://eparlib.sansad.in/bitstream/123456789/{doc_id}/1/{filename}`

---

## Admin UI (`/admin`) — ✅ DONE

Flask Blueprint (`app/admin.py`) mounted at `/admin`. Features:

- **Dashboard** — stat cards (catalog total, downloaded, ready-to-dl, unresolved, registered PDFs, statements) + recent downloads + collection/debate-type breakdowns
- **Catalog** — AJAX-paginated table of all catalog items; filter by collection, language, status, debate type, date range, title keyword
- **Scraper** — trigger playwright_scraper phases (catalog/resolve/download) with collection checkboxes, limit, date range; live SSE log stream
- **Parser** — trigger main.py --parse-only (+ optional --translate); show registered PDFs + parse status; live SSE log

All jobs run as background subprocesses, stdout streamed live to browser terminal widget.

GitHub issue: #42

---

## New UI Vision — v2 redesign

**See docs/UI_DESIGN.md for full spec.** Summary:

### 1 — Wiki (knowledge graph)
Each "entity" (person, topic, event, place, bill) has its own page that cross-links to everything else. Like Wikipedia, but every claim links back to the exact Lok Sabha statement that supports it.

- `/wiki/person/{slug}` — MP profile: party, constituency, all statements, key positions, rhetoric over time
- `/wiki/topic/{slug}` — Topic page: timeline of all Parliament debates on a topic across sessions + speakers
- `/wiki/event/{slug}` — Major events (budget presentation, no-confidence vote, presidential address)
- `/wiki/bill/{slug}` — Bill page: every reading, amendments, who spoke for/against
- Every statement on every page links back to its source PDF page

DB additions needed: `entities` table + `entity_mentions` linking statements ↔ entities. Claude extracts entities at parse time.

### 2 — News (context-first, Claude at parse time)
Instead of generating a gist AFTER parsing, Claude runs DURING the parse pipeline:
1. As statements are extracted, Claude identifies the 3–5 key stories of the day
2. For each story, Claude queries past statements (same topic/speaker) for context
3. Claude writes a full news article with historical context embedded — not a summary
4. Article stored in `news_articles` table, shown on home page

Result: every news item already has "this connects to X said in 2024" baked in, not added later.

### 3 — Forum (data-backed discussion)
Each news article + wiki page has a threaded discussion section. Users can ask questions in free text ("when did BJP last raise this?") and the system queries the DB (FTS5 + eventually vector search) to surface relevant past statements.

- `discussions` table + `posts` table
- "Research thread" UI: question → AI finds relevant statements → community annotates
- Turns the site from read-only into a collaborative intelligence tool

---

## Known issues / decisions

- **eparlib blocks requests** — Use playwright_scraper.py (real Chromium browser).
- **Hindi PDF parser** — pdf_parser.py extracts 0 statements from Devanagari PDFs. Needs separate Hindi-aware extraction path (pdfminer or tesseract OCR for scanned pages).
- **Large PDFs time out in Cowork sandbox** — Files >5MB must be parsed on local machine.
- **Session 7 dates** — Jan 28–29 2026 PDFs exist but dates not in sessions_data.py. Add them.
- **DB schema** — `statements` has `original_text`/`original_language` for translations; `catalog` has `debate_type`, `lok_sabha_no`, `session_no`; `digests` caches Claude summaries.

---

## Roadmap

### In progress / next
- [ ] Fix Hindi PDF parser — extract text from Devanagari PDFs
- [ ] Test Sarvam AI translation locally (`python parser/test_sarvam.py`)
- [ ] Add Session 7 sitting dates (Jan 28–29 2026) to sessions_data.py
- [ ] **UI v2** — Wiki + News + Forum (see docs/UI_DESIGN.md for spec)

### Scrapers
- [ ] Run --catalog to build full item index (6,458+ debates)
- [ ] --resolve + --download for all 18th LS PDFs
- [ ] Add Rajya Sabha debates
- [ ] Verify sitting dates Sessions 1, 2, 3, 5

### Parser
- [ ] Hindi-aware PDF extraction path
- [ ] Entity extraction at parse time (people, topics, bills, events)
- [ ] Improved topic detection

### App v2 (UI redesign)
- [ ] `entities` + `entity_mentions` DB tables
- [ ] Wiki blueprint (`/wiki`)
- [ ] News blueprint (Claude at parse time, `news_articles` table)
- [ ] Forum/discussion blueprint (`/discuss`)
- [ ] Party affiliation lookup (ECI data)

### Later
- [ ] Migrate SQLite → Postgres (Neon) for production
- [ ] Deploy on Railway/Render
- [ ] REST API (FastAPI)
- [ ] Historical sessions (1st–17th Lok Sabha)
- [ ] Courts + Tenders data cross-joins
- [ ] YouTube transcript matching
