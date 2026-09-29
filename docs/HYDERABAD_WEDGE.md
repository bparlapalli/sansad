# ParamaSrota — Hyderabad Wedge (plan v1)

*Written 2026-09-29. Applies `STORY_ENGINE.md` to one city. Read that first.*

> **The Story Engine stays the foundation. Hyderabad real estate is the first wedge with a
> paying user. Every blog post in this plan shares place, actor and policy nodes, so the wiki's
> reuse ratio climbs by design.**

---

## 1. Why this wedge

- **Buyer with money and an information gap:** NRIs (especially the US Telugu IT diaspora) buying
  in Hyderabad from a distance, relying on brokers and WhatsApp rumours.
- **Founder-market fit:** the founder is part of that diaspora — distribution through NRI WhatsApp
  groups and Telugu associations, not SEO.
- **Nobody answers "why did this area grow, and what's next?"** Listing sites show asking prices.
  India has no MLS, registered values often understate real prices, land records are fragmented.
  Don't build Zillow; build the *why* layer Zillow can't.
- **Same engine, forward-looking:** past stories explain the forces; the product asks which forces
  are lining up now, per micro-market.

**Guardrails:** buyer-side only (no developer money, no paid placements). Analysis, not "buy
here" advice. Every risk claim sourced.

## 2. The cluster (hub-and-spoke)

**Hub node:** Hyderabad. **Shared sub-hubs** every post should touch at least one of:
IT corridor / Cyberabad · Infrastructure (ORR, Metro, RRR) · State policy (IT policy, GOs,
HMDA master plan) · Enforcement / risk (HYDRAA, lake FTL/buffer zones) · Diaspora & US links.

### Core posts (the wedge)

| # | Question | Key nodes (role) | Reuse into |
|---|---|---|---|
| 1 | **Why did West Hyderabad win?** (Gachibowli → Financial District → Kokapet) | State IT policy (deliberate bet), ORR (deliberate bet), HITEC City, IT firms' arrival (spillover) | Hub post — everything links here |
| 2 | **GO 111 and HYDRAA: the unblocker and the outlet valve** | GO 111 repeal 2022 (unblocker), HYDRAA demolitions 2024– (roadblock), lake FTL rules | Every micro-market report's risk section |
| 3 | **What happens when a US visa rule lands in Hyderabad?** H-1B cost changes → GCC expansion → office absorption → housing demand near Financial District | US visa policy (wildcard/spillover), GCCs (spillover), returning NRIs | Diaspora hook; US comparison posts |
| 4 | **Next corridor? Kollur/Tellapur vs Shamshabad vs Kokapet** | RRR, Metro extensions, Pharma City, Musi riverfront (pending triggers) | Becomes the first paid micro-market report |

Post 3 is a **hypothesis chain** until each link is sourced — publish only the graded facts and
attributed claims; keep the causal chain labelled as such. Verify current status of every visa
rule before publishing (litigation and revisions are likely).

### Tail posts (grow the wiki, cheap with agents)

| Post | Why it's worth it | Nodes it reuses |
|---|---|---|
| **Niloufer Cafe: how an Irani café became a brand** | Viral-friendly, culturally loved, great images/quote cards | Hyderabad places, IT-workforce demand, café culture |
| **T-Hub: what a state-built startup hub did (and didn't) do** | Policy + startup crowd; T-Hub 2.0 sits in Raidurg | State IT policy, Raidurg/Financial District, actors from post 1 |
| **Why Hyderabad and not Chennai/Pune for IT?** | Comparison-case method made visible | Post 1 nodes |
| **Austin vs Hyderabad: two tech-boom housing markets** | US data is open and rich — builds method templates | Post 1, post 3 |

**Rule for tail posts:** at most 1 in 3 posts is tail; each must reuse ≥ 3 existing nodes. US
content only as a comparison case tied to a Hyderabad question — never standalone US coverage.

## 3. The paid product (test by post 4)

**Micro-market report** — one area, ~10 pages:
growth drivers (graded timeline) · pending triggers with dates · risks and outlet valves
(enforcement, lake zones, stalled approvals, litigation) · RERA project status in the area ·
comparable-area contrast · sources for every claim.

**First test:** 10 NRI buyers from personal/WhatsApp networks. Free report for feedback, then a
price test. Signal to watch: do they forward it, and do they ask for another area?

**Later:** alerts per micro-market (new GO, tender, RERA filing, enforcement action).

## 4. Sources (verify access + terms per source before scraping)

**Hyderabad:** Telangana RERA filings · Telangana GO issues portal · HMDA master plans/notices ·
registration/market-value data (IGRS Telangana — check what's publicly accessible) · Metro/RRR
project documents and tenders · HYDRAA notices · published broker research (cite, don't copy) ·
listings (asking prices only; respect ToS).

**US (comparison/method):** Zillow Research and Redfin Data Center downloads · BLS · USCIS H-1B
data · Census ACS.

## 5. Agent roles

| Agent | Job |
|---|---|
| Source monitors | One per source; pull new GOs, filings, tenders, notices |
| Extractors | Turn documents into candidate nodes (date, actor, action, place, source span) |
| **Verifier** (independent) | Must locate the exact source span before a node gets an evidence grade |
| Drafters | Draft story and wiki page text from graded nodes |
| **Founder** | Edge roles and weights, final publish decision on every post |

Verification — not collection — is the bottleneck. Budget review time accordingly.

## 6. Metrics

- Reuse ratio per post (target: rising; post 4 should reuse most of posts 1–3)
- Record pages cited 2+ times
- NRI report test: forwards, repeat requests, first payment
- Citations: backlinks, AI-engine referrals, AI crawler hits per page

## 7. Phase 2: more cities (Bengaluru, Pune, Chennai, Gurgaon)

**Hyderabad first. Other cities come in stages, not all at once.**

1. **Now: comparison cases only.** Other cities appear inside Hyderabad posts ("why Hyderabad
   and not Chennai/Pune?"). Their wiki pages are built as a side effect, cheaply.
2. **City template.** Every city uses the same sub-hubs: IT corridor, infrastructure, state
   policy, enforcement/risk, diaspora. This keeps them comparable.
3. **National nodes connect cities.** RERA Act 2016, GCC growth, H-1B and US job market, IT
   industry cycles, interest rates. Reuse *across* cities is the strongest proof of the platform.
4. **Order:**
   - **Bengaluru** — closest comparison, biggest NRI overlap.
   - **Pune** — IT plus manufacturing mix.
   - **Chennai** — slower, steadier growth; a useful contrast.
   - **Gurgaon** — developer-led vs Hyderabad's state-led model; the sharpest contrast.
5. **Gate:** open a second city only when the Hyderabad micro-market report has paying users
   and a new report costs clearly less to produce than the first one did.

## 8. Wiki pages: attributes for every entity

**Principle:** the post, the timeline and the wiki pages are three views of the *same* node and
entity tables. Nothing is written twice: fill the attributes once, and each wiki page is
generated from them. Every attribute carries a source, a date and an evidence grade.

### Entity templates (Hyderabad v1)

| Entity | Core attributes | Shows on page |
|---|---|---|
| **Area / micro-market** | name, aliases, zone, municipal body, lat/long, lake/FTL exposure, metro/ORR/RRR distance | timeline of nodes affecting it, active RERA projects, pending triggers, risks, "Cited in N stories" |
| **Policy / GO** | GO number, date, issuing department, what it changed, areas affected, current status (in force / amended / challenged) | before/after, areas affected, role in each story (unblocker, roadblock…) |
| **Infrastructure project** | name, announced date, sanctioned date, status, expected completion (with source), agency, areas served | status history (announced → sanctioned → tendered → built), delays |
| **Developer / organisation** | name, RERA registrations, projects by area, orders or enforcement actions against them, public statements | project list by area, dated actions — facts only |
| **Person** (official, politician) | name, role *on each date*, party on each date, decisions attributed to them | dated decisions and quotes, each with source |
| **Event** (enforcement drive, court ruling, announcement) | date, actor, action, areas affected, outcome | links to every area, policy and org it touched |
| **Quote** | speaker, role and party on that date, venue, date, original language + translation, source link | as a quote card with its source |

### Rules

- **Store everything, publish selectively.** Private stubs keep all attributes; the publish gate
  only controls display.
- **Developers and people: recorded facts only** (filed, said, ordered, sanctioned, delayed). No
  scores, rankings or inferred wrongdoing.
- **Dated attributes, not current snapshots.** Roles, parties, project status and GO status all
  change; keep history, never overwrite.
- **Every story node must resolve to an entity page**, even if that page stays private this week.

## 9. Order of work

1. Post 1 (hub) + its wiki pages
2. Post 2 (risk) — the section buyers value most
3. Niloufer (tail, shareable) → tests the quote/image card format
4. Post 3 (US visa → Hyderabad)
5. Post 4 → first micro-market report → NRI test
6. T-Hub, comparisons as the cadence allows
