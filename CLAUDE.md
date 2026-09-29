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
│   └── pib/                 # pib.gov.in press releases (second data source)
│       ├── pib_scraper.py       # ✅ list (ASP.NET postback per day) + fetch release pages → pib_releases
│       └── explore_pib.py       # Original Playwright probe — superseded, kept for reference
│   └── youtube/             # Party + leader YouTube channels (third data source)
│       ├── youtube_scraper.py   # ✅ list channel tabs → fetch metadata + captions → media_items/media_chunks
│       └── explore_transcripts.py # Original feasibility probe — superseded, kept for reference
│
├── core/party_registry.py   # WHO we track off-floor: parties, people, dated affiliations, accounts (edit + --seed)
├── core/sources.py          # Source registry — feeds /feed and /t/<topic> (see Known issues § Multi-source)
├── parser/
│   ├── pdf_parser.py        # Text extraction + speaker attribution + language detection
│   ├── chunker.py           # Splits a statement into ~60-word search chunks (chunks_fts)
│   ├── translator.py        # Sarvam AI (Hindi/regional → English)
│   ├── pipeline.py          # Orchestrates parse + translate + chunk + store — THE live parse path
│   ├── backfill_chunks.py   # One-time: chunk statements parsed before chunking existed
│   ├── export_public_db.py  # Trims sansad.db to last N days → public.db (for deployment)
│   └── test_sarvam.py       # Quick Sarvam API connectivity test (run locally)
│
├── app/
│   ├── app.py               # Flask app (registers all blueprints)
│   ├── admin.py             # ✅ Admin blueprint — scraper, catalog, parser, AI generation
│   │                         #    (never registered when APP_ENV=production — no auth of its own)
│   ├── search_bp.py         # ✅ Search blueprint — date/politician/party/text modes
│   ├── feed_bp.py           # ✅ /feed running list, /pib + /pib/<prid>, /t/<topic> topic hub
│   ├── ingest_bp.py         # POST /ingest/db — token-gated endpoint that receives public.db
│   ├── digest.py            # Claude API daily digest + politician profile generator
│   ├── query.py             # Search functions (used by app + CLI)
│   └── templates/           # Jinja2 HTML templates
│       ├── base.html        # Shared masthead + nav
│       ├── home.html        # Today's digest + proceedings
│       ├── search.html      # Unified search (4 modes) — shows matching chunk, not full statement
│       ├── how_to_use.html  # Public-facing "how to use this site" page
│       ├── speaker.html     # MP profile + AI profile card
│       ├── speakers_list.html # All MPs grid with filter
│       ├── sessions.html    # Session overview
│       ├── stats.html       # DB statistics
│       ├── topic.html       # Topic deep-dive with timeline (NOT yet chunked — see Known issues)
│       ├── pdfs.html        # Registered PDF list
│       └── news.html        # Latest news briefing
│
├── main.py                  # Full pipeline entry point (scrape + parse + AI)
├── daily_update.py           # Local daily job: scrape → parse+chunk → export_public_db → push_public_db
├── push_public_db.py         # Sends public.db to the live site's /ingest/db (never via GitHub)
├── sync_github_issues.py     # Idempotent roadmap → GitHub issues sync (no token in file; uses GITHUB_PAT or git creds)
├── run_stats.py             # CLI stats dashboard (run from Windows cmd)
├── export_for_ai.py         # Export statements + top MPs to JSON for AI generation
├── seed_parties.py          # One-time seed: party affiliations into members table
├── ai_content.sql           # AI-generated digests + profiles (run in DB Browser)
├── render.yaml               # Render web service config (build/start command, env vars)
├── docs/
│   ├── PROJECT_BRIEF.md     # Non-technical baseline for product/marketing/UI chats (claude.ai Project knowledge)
│   ├── TIMELINE_UI_IDEAS.md # UI directions for timelines (story / swimlanes / chapters, evidence language, lens)
│   ├── ISSUE_TIMELINES.md   # Timeline concept: fact/claim/hypothesis layers, evidence, linking, open decisions
│   ├── PRODUCT_STRATEGY.md  # Marketing + investor reviews (2026-09-28), recommended path, go/no-go gates
│   └── timelines/           # PUBLIC edition of issue-timeline data (facts + claims) + rejected UI prototype
│       └── build_public_edition.py  # regenerates it from data/timelines/ with leak checks
├── data/                    # LOCAL ONLY (gitignored): data/timelines/ = research edition incl. hypotheses
├── pdfs/                    # Downloaded PDF files
├── sansad.db                # SQLite database — full local archive (do not commit)
├── public.db                # Trimmed export for deployment (do not commit — regenerate anytime)
└── requirements.txt
```

Every sub-package adds `_ROOT = Path(__file__).resolve().parent[.parent]` to `sys.path`,
so `from core.db import ...` works regardless of where you run from.

**Note**: A legacy `db.py` exists at the project root (kept for `main.py` backward compat).
The canonical schema lives in `core/db.py` — that is what the Flask app uses.

**Import gotcha**: there's a root-level `parser.py` (legacy, primitive, no Hindi/CID support) *and* a
`parser/` package — Python's import system resolves `from parser import parse_pdf_file` (used by `main.py`)
to the **package** (`parser/__init__.py` → `parser.pipeline.parse_and_translate`), not the root file, even
though the root file also defines a function with a similar name. Confirmed empirically — don't assume from
filenames which one actually runs. The real live parse path for `main.py --parse-only` (and the Admin UI's
Parser trigger, which just runs `main.py --parse-only` as a subprocess) is:
`main.py` → `parser/__init__.py` → `parser/pipeline.py::parse_and_translate` → its own
`_store_with_translations()` (NOT `parser/pdf_parser.py::store_statements`, which is a separate insert path
only used when `pdf_parser.py` is invoked directly). Chunking (see below) is wired into `pipeline.py`'s store
function for this reason.

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

# ── PIB press releases (plain HTTP, no browser; needs `truststore`) ──────────
python scrapers/pib/pib_scraper.py                 # today (list + fetch bodies)
python scrapers/pib/pib_scraper.py --days 7        # last 7 days
python scrapers/pib/pib_scraper.py --from 2026-09-01 --to 2026-09-28
python scrapers/pib/pib_scraper.py --list-only --days 30   # index only
python scrapers/pib/pib_scraper.py --fetch-only --limit 200
python scrapers/pib/pib_scraper.py --status

# ── Party & leader YouTube (yt-dlp, no API key; needs `truststore`) ──────────
python scrapers/youtube/youtube_scraper.py --seed               # load core/party_registry.py
python scrapers/youtube/youtube_scraper.py --days 30            # list + fetch captions, all accounts
python scrapers/youtube/youtube_scraper.py --days 30 --party inc
python scrapers/youtube/youtube_scraper.py --account @RahulGandhi --days 7
python scrapers/youtube/youtube_scraper.py --list-only --days 30
python scrapers/youtube/youtube_scraper.py --fetch-only --limit 50 [--english]
python scrapers/youtube/youtube_scraper.py --status

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

# ── Backfill search chunks (one-time, only needed after upgrading old data) ──
python parser/backfill_chunks.py             # chunk statements parsed before chunking existed

# ── Daily local update + push to live site ────────────────────────────────────
python daily_update.py                       # scrape → parse+chunk → export → push
python daily_update.py --skip-scrape         # just re-parse/export/push
python parser/export_public_db.py --days 30  # build public.db by hand
python push_public_db.py                     # push public.db to LIVE_SITE_URL (needs .env)
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
| `statement_chunks` | ~60-word, sentence-safe slices of each statement — what search actually matches |
| `chunks_fts` | FTS5 virtual table over statement_chunks |
| `pib_releases` | PIB press releases — keyed by PIB's `prid`; `fetch_status` listed → fetched/error; `translations` = JSON {language: prid} |
| `pib_releases_fts` | FTS5 over pib_releases (title, ministry, body_text) — insert/update/delete triggers keep it in sync |
| `parties` | Parties/movements tracked off-floor (inc, bjp, cjp) — seeded from `core/party_registry.py` |
| `people` | One row per leader *for life* — no party column; `aliases` (JSON) match video titles; `member_id` links to their Parliament record |
| `affiliations` | person × party × [start_date, end_date] — the ONLY place party membership lives; handles party switches |
| `source_accounts` | platform (youtube/x/website) + handle, owned by a party or a person; `verified`, `active`; `kind='search'` for people with no official channel |
| `media_items` | One video/post — `person_id` (speaker if known), `party_id` = speaker's party **on published_date** (via `party_on()`), `attribution` owner/title_match/search/none |
| `media_chunks` / `media_chunks_fts` | ~60-word timed transcript slices ("quotes") with `start_sec` for `&t=` deep links; `text_en` for translations |

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

**Current DB state** (local `sansad.db`, 2026-09-28): 3,073+ statements, 54,500+ search chunks, 100+ members. The live site shows a trimmed ~30-day subset of this (see Deployment section).

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

## Deployment — ✅ LIVE (2026-09-28)

Live at **https://sansad-b039.onrender.com** (Render free tier). Unlisted — `robots.txt` disallows all,
no password gate, not linked from anywhere public. Public "how to use" page at `/how-to-use`.

**Hard rule: the full `sansad.db` never leaves the local machine, and never goes to GitHub in any form** —
not committed, not as a Release asset, public or private. This was an explicit decision (protects the
scraped/parsed dataset as the project's actual asset — a one-click full bulk download would defeat that even
if gated). GitHub holds code and docs only — the one data exception is the *public edition* of the
issue-timeline research (`docs/timelines/`: facts + attributed claims, no hypotheses), chosen by the
founder on 2026-09-28.

**How data reaches the live site:**
1. Locally: `main.py --all-sessions` / `playwright_scraper.py` scrapes new PDFs → `main.py --parse-only`
   parses + chunks them into the full local `sansad.db` (unbounded history, grows forever, ~106MB and
   counting as of this writing).
2. `parser/export_public_db.py --days 30` copies **only** the last N days of statements (+ the members,
   chunks, source_pdfs, digests, profiles they depend on) into a small standalone `public.db`. "Last N days"
   is relative to the newest sitting date *in the data*, not wall-clock today — debate PDFs lag the real
   calendar by months.
3. `push_public_db.py` POSTs `public.db` directly to the live app's `/ingest/db` (bearer-token auth via
   `INGEST_TOKEN`, matching value set in both local `.env` and the Render service's env vars). The endpoint
   validates it's a real statements DB, then atomically swaps it in (`app/ingest_bp.py`).
4. `daily_update.py` chains all of the above into one command, meant for a Windows Task Scheduler entry
   (**not yet set up** — see Roadmap). Until then, run it by hand.

**Render service config** (`render.yaml`):
- `buildCommand: pip install -r requirements.txt`
- `startCommand: python -m gunicorn app.app:app --bind 0.0.0.0:$PORT` — use `python -m gunicorn`, not bare
  `gunicorn`; the bare binary wasn't resolvable on PATH in Render's venv even though pip install succeeded.
- Env vars: `APP_ENV=production` (hides `/admin`), `SANSAD_DB_PATH=/opt/render/project/src/public.db`,
  `INGEST_TOKEN` (set manually in the dashboard, `sync: false` — never committed).
- **No persistent disk.** Free tier, ephemeral filesystem. Data survives idle spin-down/spin-up fine; it's
  only wiped by an actual redeploy (a `git push` to `main`, or a manual redeploy). Re-run `push_public_db.py`
  once after any code deploy to refresh the data.
- `/admin` is only registered in `app/app.py` when `APP_ENV != production` — it spawns local subprocesses
  and has zero auth of its own, must never be reachable in production.

**Old `.github/workflows/scraper.yml` is disabled** (schedule removed, `workflow_dispatch` only) — it used
the legacy request-based `scraper.py` (blocked by eparlib) and committed `sansad.db` to git (harmless only
because `*.db` is gitignored — the intent was wrong regardless, now that data is local-only by policy).

---

## Known issues / decisions

- **eparlib blocks direct requests** — Use playwright_scraper.py (real Chromium browser).
- **PIB works with plain HTTP, but TLS needs `truststore`** — pib.gov.in doesn't send its intermediate
  cert, so Python's default bundle rejects it (curl on Windows works because it uses the OS store).
  `pib_scraper.py` injects `truststore`; never "fix" this with `verify=False`. On this machine pip itself
  also failed TLS to PyPI — `python -m pip install --use-feature=truststore <pkg>` works around it.
- **PIB listing = ASP.NET WebForms postback** — GET `allRel.aspx?reg=3&lang=1`, then POST back the
  `__VIEWSTATE` fields with day/month/year set. Region 3 = PIB Delhi (the national feed). Each language
  version of a release has its own PRID; we store English and record the others in `translations`.
- **Multi-source architecture** — `core/sources.py` is a registry: each source (Parliament, PIB, later
  YouTube…) registers a `recent()` and a `search()` returning a common Item shape. `/feed` (running list)
  and `/t/<topic>` (topic hub: per-source hits + merged timeline) are built on it, so a new source appears
  in both automatically. Only a source-specific browse page (like `/pib`) needs its own route in
  `app/feed_bp.py`. To add a source: scraper → table (+FTS with triggers) → register in `core/sources.py`
  → add its rows to `export_public_db.py` → add a step to `daily_update.py`.
- **PIB in production** — `export_public_db.py` copies fetched `pib_releases` for the last N days
  (window measured from the newest PIB release, not the debate lag); `daily_update.py` scrapes the last 3
  days of PIB each run. Historical backfill stays local until we decide what the live site should hold.
- **YouTube source (party & leader channels)** — `scrapers/youtube/youtube_scraper.py`, registry in
  `core/party_registry.py`. Design points:
  - *Party-switching*: a person's party is never stored on the person — only in dated `affiliations`
    rows. Each `media_items` row is stamped with `party_on(person, published_date)`, so old quotes stay
    under the old party. Scindia (INC → BJP 2020-03-11) is seeded as the worked example.
  - *Attribution*: a leader's own channel → the owner. Party channel → the tracked person named
    earliest in the title (aliases incl. Hindi), else unattributed; party-channel videos are only kept
    if they name a tracked leader or look like a press conference/briefing. Party pressers have several
    speakers, so title attribution is "primary speaker", not per-sentence.
  - *Press conferences are livestreams* → on the channel's `/streams` tab, not `/videos`. Both are walked.
  - *Impostor handles*: YouTube `@INCIndia` and `@priyankagandhivadra` are NOT official. Only handles
    resolved and checked (name + subscriber count) are `verified=1`; X/website accounts are recorded
    but `active=0` (unverified, from memory) until someone checks them.
  - *CJP (Cockroach Janta Party)*: a movement, not a registered party (founded 2026-05-16 by Abhijeet
    Dipke). No verified official YouTube channel; `@CockroachRevolution2029` looks fan-run. Dipke is
    tracked via a `kind='search'` account (news channels' uploads) — lower confidence.
  - *Rate limit*: YouTube 429s caption downloads per IP after a burst (hit on 2026-09-28 after ~15
    probes; still blocked 25+ min later). Scraper is sequential, 4–8s between videos, backs off
    2/5/15 min, then stops leaving rows `listed`. Don't parallelise on one IP. `youtube-transcript-api`
    hits the same endpoint, so switching libraries doesn't help.
  - *Volume*: INC's `/videos` tab alone has 500+ uploads in 30 days (short clips) — `MAX_WALK` caps a tab.
  - *English*: captions are mostly Hindi ASR. `--english` also stores YouTube's machine translation
    (the `en` auto track) in `media_chunks.text_en`, at 2× caption requests.
- **Hindi PDF parser** — pdf_parser.py extracts 0 statements from Devanagari PDFs. Needs Hindi-aware extraction (pdfminer or tesseract OCR). Hindi statements parsed but not translated yet.
- **Large PDFs time out in Cowork sandbox** — Files >5MB must be parsed on local Windows machine.
- **Session 7 dates** — Jan 28–29 2026 PDFs exist but dates not yet in sessions_data.py. Add them.
- **Legacy db.py at root** — `sansad/db.py` is a legacy file used by `main.py`. Flask uses `core/db.py`. Both point to the same `sansad.db`. Do not delete the root `db.py` until `main.py` imports are updated to `from core.db import ...`.
- **virtiofs (Cowork sandbox)** — `core/db.py` detects virtiofs on Linux/macOS and uses a temp copy. On Windows it always reads sansad.db directly. The Cowork sandbox cannot read the Windows-format WAL-mode DB directly.
- **`/topic` page not yet chunked** — `search.html` (the `/search` route) shows matching `statement_chunks`, but `topic.html` (`/topic/<topic>`) still does its own FTS match against whole statements and CSS-clamps the display. Same underlying "wall of text" issue, just not fixed there yet — wasn't in scope for the search fix, flagged as a follow-up.
- **The GitHub repo (bparlapalli/sansad) is PUBLIC.** Anything committed is published. Issue-timeline
  research containing inferred links / hypotheses about named people stays in `data/` (gitignored);
  only the public edition (`docs/timelines/`, built by `build_public_edition.py`) is committed.
  `create_github_issues.py` must never be committed (it held a hardcoded PAT — found invalid/401 on
  2026-09-28; the same token was also embedded in the `origin` remote URL).
- **Issue timelines** — concept + decisions in `docs/ISSUE_TIMELINES.md`. Three layers (fact / attributed
  claim / internal hypothesis), evidence computed from independent sources, everything-is-a-node linking.
  The single-file UI prototype was **rejected as unusable** by the founder (2026-09-28); keep the JSON
  schema, redesign the UI. Not yet in the DB or Flask app.
- **Strategy** — `docs/PRODUCT_STRATEGY.md`: both reviews say the product is sourced, party-dated quotes
  (+ alerts), not the hidden-links map; hypotheses stay internal; prove a paid pilot by day 90.
- **`sansad.db` is not gitignored by accident** — it (and `public.db`) must stay gitignored. If either ever shows up in `git status` as trackable, something is wrong; do not commit them (see Deployment § hard rule above).

---

## Roadmap

### Done (2026-09-28 session)
- [x] Chunk-level search (`statement_chunks` + `chunks_fts`) — search shows the matching paragraph, not the whole speech
- [x] Live deployment on Render (free tier) — see Deployment section above
- [x] Local-only full DB + trimmed rolling-window public export/push pipeline
- [x] `/admin` gated out of production; `robots.txt` disallow-all
- [x] Public "how to use this site" page (`/how-to-use`, mirrored in `docs/HOW_TO_USE.md`)

### Done (2026-09-28, later session)
- [x] YouTube party/leader source + party registry with dated affiliations (see Known issues § YouTube)
- [x] Issue-timeline concept, research data for 3 issues, public/local editions (docs/ISSUE_TIMELINES.md)
- [x] Marketing + investor review → docs/PRODUCT_STRATEGY.md

### In progress / next
- [ ] YouTube caption backfill — 1,245 videos listed, 0 fetched (IP rate-limited 2026-09-28); rerun
      `youtube_scraper.py --fetch-only`, consider `--cookies-from-browser firefox`
- [ ] Alerts + daily brief product (person/topic watch, email/WhatsApp) — strategy's first paid product
- [ ] Quote cards (permalink + source + party-on-date) and dossier export
- [ ] Methodology + corrections page
- [ ] Issue-timeline UI redesign (prototype rejected) → then DB tables + `/issues/<slug>` blueprint
- [ ] Topic registry + miner + candidate review queue (`/admin/candidates`)
- [ ] **Set up Windows Task Scheduler** to run `daily_update.py` automatically — currently run by hand
- [ ] Apply chunking to `/topic` page too (currently only `/search` shows chunks — see Known issues)
- [ ] Fix Hindi PDF parser — extract text from Devanagari PDFs (pdfminer/tesseract path)
- [ ] Test Sarvam AI translation locally (`python parser/test_sarvam.py`)
- [ ] Add Session 7 sitting dates (Jan 28–29 2026) to sessions_data.py
- [ ] Set `ANTHROPIC_API_KEY` in `.env` to enable on-demand AI generation
- [ ] **UI v2** — Wiki + News + Forum (see docs/UI_DESIGN.md for spec)

### Scrapers
- [x] PIB press release scraper (`scrapers/pib/pib_scraper.py`) → `pib_releases` in local sansad.db
- [ ] PIB: backfill history, add to `daily_update.py`, surface in web UI + public export
- [x] YouTube: party + leader channels (INC, BJP, CJP) → `media_items` + timed quote chunks; in /feed, /t/<topic>, export, daily_update
- [ ] YouTube: person/party pages (`/person/<slug>`) joining Parliament statements + off-floor quotes
- [ ] X/Twitter: API is paid ($) — decide; handles already in the registry (`active=0`)
- [ ] Party websites: inc.in / bjp.org press releases — plain HTML scrapers, same pattern as PIB
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
- [ ] REST API (FastAPI)
- [ ] Historical sessions (1st–17th Lok Sabha)
- [ ] Courts + Tenders data cross-joins
- [ ] YouTube transcript matching
