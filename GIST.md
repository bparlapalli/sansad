# ParamaSrota — Project Gist
*Paste this at the start of every new session to restore full context.*
*Last updated: April 2026, Session 1*

---

## What this project is

**ParamaSrota** ("the great source") is a political intelligence platform for India.

**Positioning:** "I am the database for people to find Indian government data easily" — the Google for Indian government data. Not a news site. Not a BI tool. The structured, searchable, connected source for govt data.

**GitHub repo:** https://github.com/bparlapalli/sansad

**Owner skills:** Strong Python, strong Snowflake + data engineering. No frontend — use Streamlit for UI.

---

## Core insight

Parliament data alone is a dataset. Cross-wiring **politicians ↔ courts ↔ YouTube ↔ newspapers ↔ tenders ↔ companies** creates a political intelligence graph. The exponential value lives at the intersections — signals invisible in any single source. The "fuzziness" of these joins is real and correct — they are probabilistic entity matches, not SQL foreign keys.

---

## Current codebase — what exists

Working Python pipeline for Lok Sabha debate PDFs. All local, no web layer.

| File | What it does |
|------|-------------|
| `scraper.py` | Downloads PDFs from eparlib.sansad.in. Doc_id anchor + probe logic (±150 IDs, step 25). Browser headers, retry/backoff. |
| `parser.py` | Regex speaker detection (SHRI/SMT/DR patterns). Splits pages into attributed statements. |
| `db.py` | SQLite schema: sessions, sitting_dates, source_pdfs, members, statements, statements_fts (FTS5). |
| `query.py` | CLI search: by speaker, FTS5 full-text, stats. |
| `sessions_data.py` | 18th Lok Sabha sessions 1–6, sitting dates, doc_id anchors. |
| `main.py` | Orchestrates: init_db → run_scraper → parse_pdfs. |

### Known gaps
- Parser skips Hindi statements entirely
- `classify_statement_type` too naive (length < 15 words = interruption)
- No party affiliation in members table
- No monitoring/alerting on scraper failures
- `IDS_PER_DAY = 40` will drift as eparlib upload patterns change
- No Rajya Sabha sessions yet

---

## Architecture decisions (finalised)

### Medallion per source
Every source gets Bronze → Silver → Gold:
- **Bronze** — raw HTML/PDF/JSON, immutable, S3/GCS
- **Silver** — parsed, typed, deduped → Postgres (recent 90 days) + Snowflake (full history)
- **Gold** — entity-resolved, canonical IDs, JOIN-ready → Snowflake via DBT

### Two-layer production design
- **App layer:** Postgres (Neon) → FastAPI → Streamlit. Fast queries. Free tier.
- **Intelligence layer:** Snowflake + DBT. Full history. Gold joins as Snowflake views. Paid tier.

### Entity resolution = the moat
Canonical `politician_id` across all sources. Fuzzy name matching. "Rajnath Singh" = "Sh. Rajnath Singh, MP" = "rajnath_singh" → `POL_00423`. Once built, cannot be replicated cheaply.

### Intelligence intersections
- Politician + Courts → criminal exposure, pending cases
- Courts + Tenders → blacklisted bidders still winning
- Politician + Tenders → constituency award flows, related-party detection
- Triple join → emergent signals invisible in any single source
- + YouTube + News → narrative layer (statement vs record gap = the product)

---

## Monetization

### Two products on one graph

**Civic platform (free/ad-supported)**
- Politician profile pages → SEO traffic engine
- Claim checker (news quote vs parliament record) → viral
- Tender search → Google-indexed traffic
- Revenue: AdSense, election season spikes

**Tender + political BI (paid)**
- Tender alerts: keyword monitoring → ₹999–4999/mo
- Political risk map: company ↔ politician exposure → PE/VC
- Data API: fintechs, ESG → pay per call

### Data tiers
| Tier | Content | Price |
|------|---------|-------|
| Free | Last 7 days · last 50 statements per speaker | Ad-supported |
| Prosumer | Full history · exports · cross-source search | ₹499/mo |
| B2B | Snowflake · API · alerts · risk scores | ₹2k–50k/mo |

**Fastest revenue path:** Tender alert emails → direct LinkedIn outreach to 10–20 infra/pharma companies. No traffic needed. First paying customers before SEO kicks in.

---

## MVP launch sequence

1. **Week 1–2:** SQLite → Postgres (Neon) + Streamlit app + Railway deploy
2. **Week 3–4:** S3 bronze stage + Snowflake trial + first DBT silver model
3. **Week 5+:** Court scraper + Tender scraper + entity resolution + intelligence views

---

## Docs added to repo (Session 1)

`docs/ARCHITECTURE.md` + 4 SVG diagrams in `docs/diagrams/`:
- `01_medallion_architecture.svg`
- `02_intelligence_intersections.svg`
- `03_traffic_monetization.svg`
- `04_production_architecture.svg`

---

## Task board

**Tool:** GitHub Projects on bparlapalli/sansad repo
**4 swim lanes:** Scraper · Database · Intelligence · UI
**32 tasks created** (see GitHub Projects for current status)

### Critical path to MVP (do in order)
1. [DB] Migrate SQLite → Postgres (Neon)
2. [UI] Streamlit app: politician search + last 7 days free
3. [UI] Deploy on Railway
4. [SCRAPER] Add monitoring + alerting
5. [DB] Snowflake trial + S3 bronze stage
6. [DB] DBT silver models
7. [SCRAPER] Court scraper adapter
8. [SCRAPER] Tender scraper (GeM)
9. [INTEL] Entity resolution: politician_id
10. [INTEL] Intelligence Snowflake views

---

## Working conventions

- Claude writes code, you review and deploy
- Strategy discussions in Claude → break into tasks → add to GitHub Projects
- Each session starts with this gist pasted in
- Gist updated at end of each session (wind-down)
- No full web apps built inside Claude chat — keep it to code, diagrams, analysis
- Diagrams go in `docs/diagrams/` in the repo as SVGs
