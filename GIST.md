# ParamaSrota — Project Gist
*Paste this at the start of every new session to restore full context.*
*Last updated: April 2026, Session 3*

---

## What this project is

**ParamaSrota** (“the great source”) is a political intelligence platform for India.

**Positioning:** “I am the database for people to find Indian government data easily” — the Google for Indian government data. Not a news site. Not a BI tool. The structured, searchable, connected source for govt data.

**GitHub repo:** https://github.com/bparlapalli/sansad

**Owner skills:** Strong Python, strong Snowflake + data engineering. No frontend — use Streamlit for UI.

---

## Core insight

Parliament data alone is a dataset. Cross-wiring **politicians ↔ courts ↔ YouTube ↔ newspapers ↔ tenders ↔ companies** creates a political intelligence graph. The exponential value lives at the intersections — signals invisible in any single source. The “fuzziness” of these joins is real and correct — they are probabilistic entity matches, not SQL foreign keys.

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
| `main.py` | Orchestrates: init_db → run_scraper → parse_pdfs. Flags: `--parse-only`, `--all-sessions`, `--max-pdfs N`, `--dates`. |
| `status.py` | FastAPI status dashboard. Run: `uvicorn status:app --reload --port 8001`. Routes: `/` (HTML dark-mode dashboard), `/api/status` (JSON). Shows PDF count, statement count, session coverage progress bars, per-PDF parse stats. Auto-refreshes 5 min. |

### Known gaps
- Parser skips Hindi statements entirely
- `classify_statement_type` too naive (length < 15 words = interruption)
- No party affiliation in members table
- `IDS_PER_DAY = 40` will drift as eparlib upload patterns change
- No Rajya Sabha sessions yet
- **Probe radius too wide for cron:** `PROBE_RADIUS=150`, `PROBE_STEP=25` = 26 HEAD requests × 15s timeout = up to 390s/date when eparlib blocks. With `--all-sessions --max-pdfs 5` (30 dates) this is ~3 hours worst case. Should reduce to `PROBE_RADIUS=50` (10 probes/date, ~150s/date max).

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
Canonical `politician_id` across all sources. Fuzzy name matching. “Rajnath Singh” = “Sh. Rajnath Singh, MP” = “rajnath_singh” → `POL_00423`. Once built, cannot be replicated cheaply.

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

## Files added to repo

### Session 1
`docs/ARCHITECTURE.md` + 4 SVG diagrams in `docs/diagrams/`:
- `01_medallion_architecture.svg`
- `02_intelligence_intersections.svg`
- `03_traffic_monetization.svg`
- `04_production_architecture.svg`

### Session 3 (April 2026)
- `.github/workflows/scraper.yml` — GitHub Actions cron (daily 02:00 UTC / 7:30 AM IST). Steps: download (best effort, `continue-on-error`) → parse-only → write `scraper_status.json` → upload artifact → commit `sansad.db` back to repo if no `DATABASE_URL` secret set.
- `requirements.txt` — pdfplumber, requests, fastapi, uvicorn, flask
- `status.py` — FastAPI status dashboard (see above)

First manual workflow run triggered Session 3: Run #1 (`workflow_dispatch`). Download step stalled on eparlib blocking — expected. Parse step should process the 3 committed PDFs once download step times out.

---

## Task board

**Tool:** GitHub Projects → https://github.com/users/bparlapalli/projects/1/views/1
**Structure:** Columns = pipeline stage (Scraper → Database → UI → Intelligence). Swim lanes = data track.
**41 tasks across 6 tracks** (see GitHub Projects for current status)

### Tracks
| Track | Items | Description |
|-------|-------|-------------|
| 🟢 Lok Sabha | 28 | Parliament debates — primary track |
| 🔵 Courts | 1 | eCourts case documents |
| 🟡 Tenders | 2 | GeM + CPPP govt tenders |
| 🟣 Private Business | 1 | Politician family business connections |
| ⚪ YouTube | 1 | Parked — privacy concerns |
| 🔴 Combined Intelligence | 7 | Cross-track, unlocked when 2+ tracks have data |

### Priority system (Now / Next / Later / Parked)

**Now — 7 items remaining (2 completed this session):**
| # | Task | Status | Why |
|---|------|--------|-----|
| ~~#40~~ | ~~GitHub Actions cron~~ | ✅ Done | `.github/workflows/scraper.yml` pushed + first run triggered |
| ~~#41~~ | ~~Scraper status dashboard~~ | ✅ Done | `status.py` pushed — run `uvicorn status:app --reload --port 8001` |
| #34 | Hindi parsing (Sarvam AI) | ⏳ | Parser-level. Unlocks ~60% of statements skipped |
| #33 | Fix scripted PDF downloader | ⏳ | Also: reduce `PROBE_RADIUS` 150→50 in `scraper.py` to speed up cron |
| #35 | Download remaining session PDFs | ⏳ | Core data gap |
| #10 | Migrate SQLite → Postgres (Neon) | ⏳ | Foundation for web layer |
| #37 | S3 bronze stage for raw PDFs | ⏳ | Cheap storage (~$0.023/GB/month) |
| #39 | Register domain | ⏳ | ~₹1,000. Do it now before someone else does |
| #29 | Tender alert email digest | ⏳ | Fastest path to first revenue — no public traffic needed |

**Next:** FastAPI (#25) · Railway deploy (#28) · Politician search (#26) · Quote cards (#36) · Monitoring (#2)

**Later:** Courts scraper · Tender scraper · Claim checker · SEO · DBT · Entity resolution

**Parked:** Snowflake trial (#11) · YouTube (#6) · DBT incremental · Cross-source join views

---

## Infrastructure cost reality (stealth mode)

| Component | Option | Cost |
|-----------|--------|------|
| Raw PDF storage | S3 Standard | ~$0.023/GB/month. 1000 PDFs ≈ pennies |
| App database | Neon Postgres free tier | Free (0.5GB, enough for MVP) |
| Analytics | **DuckDB locally** | Free. Runs on your machine. Upgrade to Snowflake only when needed |
| Snowflake | 30-day trial, then ~$25–40/month minimum | **Skip until first paying customer** |
| Hosting | Railway Hobby | $5/month |
| Domain | .in or .com | ~$10–15/year. Register now |
| **Total MVP cost** | | **~$6–8/month** |

Snowflake is the right long-term call but wrong right now. DuckDB can query S3 files locally and produce the same medallion views for free. Migrate when you’re billing customers.

---

## North star vision (as of April 2026)

A news-intelligence platform where:
- **Free tier:** latest data only (last N days) — politician quotes, tender awards, court listings
- **Token tier:** deep historical queries, cross-source connections, “what has this politician said about X company over 5 years”
- **Personalization:** user interest graph → relevant alerts
- **Ads:** minimal, served directly through app (not AdSense), targeted by interest graph
- **B2B:** Snowflake data sharing + API for fintechs, ESG funds, journalists

Think: structured Indian political data layer, not a news site. The moat is the entity graph, not the content.

---

## Working conventions

- Claude writes code, you review and deploy
- Strategy discussions in Claude → break into tasks → add to GitHub Projects
- Each session starts with this gist pasted in
- Gist updated at end of each session (wind-down)
- No full web apps built inside Claude chat — keep it to code, diagrams, analysis
- Diagrams go in `docs/diagrams/` in the repo as SVGs
