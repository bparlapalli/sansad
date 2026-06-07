# ParamaSrota — Parliament Intelligence

> *"परम श्रोता" — The Supreme Listener*

Read this file at the start of every session to get up to speed.

Scrapes Lok Sabha debate PDFs, parses attributed statements, translates Hindi/regional content to English, and presents everything as a linked wiki + live news feed with community discussion.

---

## Project structure (monorepo)

```
sansad/
├── core/                    # Shared: DB schema, sessions data
│   ├── db.py                # SQLite schema + seed + virtiofs detection. DB_PATH = root/sansad.db
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
│   ├── admin.py             # ✅ Admin blueprint — scraper, catalog, parser, AI generation
│   ├── search_bp.py         # ✅ Search blueprint — date/politician/party/text modes
│   ├── digest.py            # Claude API daily digest + politician profile generator
│   ├── query.py             # Search functions (used by app + CLI)
│   └── templates/           # Jinja2 HTML templates
│       ├── base.html        # Shared masthead + nav
│       ├── home.html        # Today's digest + proceedings
│       ├── search.html      # Unified search (4 modes)
│       ├── speaker.html     # MP profile + AI profile card
│       ├── speakers_list.html # All MPs grid with filter
│       ├── sessions.html    # Session overview
│       ├── stats.html       # DB statistics
│       ├── topic.html       # Topic deep-dive with timeline
│       ├── pdfs.html        # Registered PDF list
│       └── news.html        # Latest news briefing
│
├── main.py                  # Full pipeline entry point (scrape + parse + AI)
├── run_stats.py             # CLI stats dashboard (run from Windows cmd)
├── export_for_ai.py         # Export statements + top MPs to JSON for AI generation
├── seed_parties.py          # One-time seed: party affiliations into members table
├── ai_content.sql           # AI-generated digests + profiles (run in DB Browser)
├── pdfs/                    # Downloaded PDF files
├── sansad.db                # SQLite database (do not commit)
└── requirements.txt
```

Every sub-package adds `_ROOT = Path(__file__).resolve().parent[.parent]` to `sys.path`,
so `from core.db import ...` works regardless of where you run from.

**Note**: A legacy `db.py` exists at the project root (kept for `main.py` backward compat).
The canonical schema lives in `core/db.py` — that is what the Flask app uses.

---

## How to run

```bash
# ── First time ────────────────────────────────────────────────────────────────
pip install -r requirements.txt
pip install playwright && playwright install chromium   # for Playwright scraper
python main.py --status          # init DB + show sitting date status

# ── Playwright scraper (preferred) ────────────────────────────────────────────
python scrapers/parliament/playwright_scraper.py --catalog
python scrapers/parliament/playwright_scraper.py --resolve --limit 200
python scrapers/parliament/playwright_scraper.py --download --limit 30
python scrapers/parliament/playwright_scraper.py --status

# ── Register manually dropped PDFs ────────────────────────────────────────────
python scrapers/parliament/local_scan.py        # scan pdfs/ dir + register
python scrapers/parliament/local_scan.py --list # list registered PDFs

# ── Parse downloaded PDFs ──────────────────────────────────────────────────────
python main.py --parse-only                  # parse all pending PDFs
python main.py --parse-only --translate      # parse + Sarvam AI translation
python main.py --no-ai                       # skip AI generation step

# ── Stats (Windows cmd) ───────────────────────────────────────────────────────
python run_stats.py                          # overview, top MPs, parties, dates

# ── Export for AI generation (no API key needed) ──────────────────────────────
python export_for_ai.py                      # writes export_for_ai.json
# → attach the JSON to a Cowork/Claude session to generate digests + profiles
# → apply ai_content.sql in DB Browser for SQLite (Tools > Execute SQL)

# ── Web app ────────────────────────────────────────────────────────────────────
python app/app.py                            # opens at http://localhost:5100
#   /          → home (latest digest + proceedings)
#   /search    → unified search (date / politician / party / text modes)
#   /speakers  → all MPs grid
#   /speaker/<slug> → MP profile + AI profile + statements
#   /sessions  → session overview
#   /admin/    → Admin UI (scraper control, catalog, parser, AI generation)

# ── CLI search ────────────────────────────────────────────────────────────────
python app/query.py --stats
python app/query.py --speaker "Rahul Gandhi"
python app/query.py --search "Vande Mataram"

# ── AI content (if ANTHROPIC_API_KEY set) ────────────────────────────────────
python app/digest.py --all-dates             # generate all missing digests
python app/digest.py --all-profiles          # generate all missing MP profiles
python app/digest.py 2025-03-19 --force      # regenerate one digest
python app/digest.py --member rahul-gandhi   # regenerate one profile
```

---

## AI integrations

### Daily Digests (app/digest.py)
- Generates a markdown summary for each sitting date based on that day's statements
- Cached in `digests` table; shown on the home page
- **Two ways to generate:**
  1. Set `ANTHROPIC_API_KEY` and run `python app/digest.py --all-dates` or via Admin UI
  2. Without API key: run `python export_for_ai.py`, attach JSON to Cowork session →
     apply the generated `ai_content.sql` in DB Browser for SQLite
- Model: `claude-sonnet-4-6`
- Auto-runs on `python main.py` if `ANTHROPIC_API_KEY` is set

### Politician Profiles (app/digest.py)
- Generates a structured MP bio per politician: summary, key positions, notable quotes, parliamentary style
- Cached in `politician_profiles` table (member_id UNIQUE)
- Shown as an "🤖 AI Profile" card on each MP's speaker page
- Same two generation paths as digests above
- `key_topics` stored as JSON array; rendered as clickable search chips

### Sarvam AI (parser/translator.py)
- Key stored in `.env` as `SARVAM_API_KEY=...` (gitignored)
- API: `https://api.sarvam.ai/translate`, model `mayura:v1`
- Supports: hi, bn, te, mr, ta, gu, kn, ml, pa, or
- Enable per-run: `python main.py --parse-only --translate`
- **Known issue**: Hindi Devanagari PDFs (lsd files) extract 0 statements — pdf_parser.py
  needs a Hindi-aware extraction path before translation becomes useful

---

## DB Schema summary

| Table | Purpose |
|---|---|
| `sessions` | One row per Parliament session |
| `sitting_dates` | One row per calendar day Parliament sat |
| `source_pdfs` | One row per registered/downloaded PDF |
| `members` | MPs — name, name_normalized (no titles), party, constituency |
| `statements` | Core fact table — one row per attributed statement |
| `digests` | Claude-generated daily summaries (markdown) |
| `politician_profiles` | Claude-generated MP bios (markdown + JSON key_topics) |
| `member_history` | Party/constituency changes over time |
| `catalog` | eparlib item index (doc_id, title, date, filename, download status) |
| `statements_fts` | FTS5 virtual table over statements |

**name_normalized** in `members` strips honorifics (SHRI, SHRIMATI, DR., PROF., etc.) and lowercases.
Always pass `member["name_normalized"]` (not `member["name"]`) to `search_by_speaker()`.

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

## PDFs parsed / registered

| File | Session | Language | Statements | Notes |
|------|---------|----------|-----------|-------|
| `UCD_18_4_19-03-2025_Fullday.pdf` | 4 | English | ~50 | Parsed OK |
| Multiple Aug 2025 UCD files | 5 | English | ~330 | Monsoon Session Q&A |
| `lsd_18_VI_05-12-2025.pdf` | 6 | Hindi | ~450 | 15MB — parsed locally |
| `lsd_18_VI_08-12-2025.pdf` | 6 | Hindi | ~200 | 1404 pages |
| `lsd_18_VI_19-12-2025.pdf` | 6 | Hindi | 2 | Valedictory |
| `lsd_18_VII_28-01-2026_original_corrected.pdf` | 7 | Hindi | ~10 | Presidential Address |
| `lsd_18_VII_03-02-2026_original_corrected.pdf` | 7 | Hindi | ~320 | Budget Session |

**Current DB state**: ~1,800+ statements across 16 sitting dates, 100+ members

---

## Admin UI (`/admin`) — ✅ DONE

Flask Blueprint (`app/admin.py`) mounted at `/admin`. Features:

- **Dashboard** — stat cards (catalog, downloaded, registered PDFs, statements, digests, profiles) + recent downloads + collection breakdowns
- **AI Generation panel** — buttons to trigger bulk digest generation and bulk profile generation; live SSE log stream
- **Catalog** — AJAX-paginated table; filter by collection, language, status, debate type, date, title
- **Scraper** — trigger playwright_scraper phases with collection checkboxes + date range; live SSE log
- **Parser** — trigger main.py parse (+ optional translate); show registered PDFs + parse status; live SSE log

All jobs run as background subprocesses, stdout streamed live to browser terminal widget.

---

## Known issues / decisions

- **eparlib blocks direct requests** — Use playwright_scraper.py (real Chromium browser).
- **Hindi PDF parser** — pdf_parser.py extracts 0 statements from Devanagari PDFs. Needs Hindi-aware extraction (pdfminer or tesseract OCR). Hindi statements parsed but not translated yet.
- **Large PDFs time out in Cowork sandbox** — Files >5MB must be parsed on local Windows machine.
- **Session 7 dates** — Jan 28–29 2026 PDFs exist but dates not yet in sessions_data.py. Add them.
- **Legacy db.py at root** — `sansad/db.py` is a legacy file used by `main.py`. Flask uses `core/db.py`. Both point to the same `sansad.db`. Do not delete the root `db.py` until `main.py` imports are updated to `from core.db import ...`.
- **virtiofs (Cowork sandbox)** — `core/db.py` detects virtiofs on Linux/macOS and uses a temp copy. On Windows it always reads sansad.db directly. The Cowork sandbox cannot read the Windows-format WAL-mode DB directly.

---

## Roadmap

### In progress / next
- [ ] Fix Hindi PDF parser — extract text from Devanagari PDFs (pdfminer/tesseract path)
- [ ] Test Sarvam AI translation locally (`python parser/test_sarvam.py`)
- [ ] Add Session 7 sitting dates (Jan 28–29 2026) to sessions_data.py
- [ ] Set `ANTHROPIC_API_KEY` in `.env` to enable on-demand AI generation
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
