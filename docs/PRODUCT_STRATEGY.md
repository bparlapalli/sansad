# Product strategy — is this worth pursuing, and what is the product?

*2026-09-28. Two independent AI-agent reviews (a product-marketing manager and a seed investor),
each told to be skeptical and to research the market. Figures below are theirs, with their
sources; not independently re-verified. Decisions are the founder's — see "Open decisions".*

## Verdicts

| | Marketing manager | Investor |
|---|---|---|
| Verdict | **Worth pursuing — as a "receipts engine"**, not a hidden-connections map | **Watch, don't invest today** |
| Hook | Searchable, attributed, timestamped quotes + alerts | Same; the identity graph over time is the long-term moat |
| First product | Public quote search + shareable quote cards; timelines as distribution | Private **"Leader & Issue Watch"**: pick 20 politicians + 5 issues → daily sourced brief + exportable dossier |
| Scale | — | ~₹70 cr (~$8M) serviceable India market → good lifestyle business (~$2M ARR at 25% share). Venture-scale only if widened to regulatory intelligence (gazette, SEBI/RBI/TRAI, courts, tenders, state assemblies) and/or USD political-risk data |
| Missing | Methodology + corrections page | An **editorial co-founder** (journalist) |

## Where they agree

1. **The product is "what India's leaders actually said, sourced to the second"** — Parliament +
   YouTube (+ PIB), Hindi and English, each quote tagged with the party the speaker was in *that
   day*. Nobody found anyone doing this for Indian politicians.
2. **Plain parliament search is commoditising** — sansad.in already searches debates from 1952;
   the government's Sansad Bhashini is adding AI transcription/translation. The edge is
   cross-source linking and dated identities, not the rows.
3. **Hidden links / hypotheses are the biggest liability** (criminal defamation, BNS s.356). Keep
   internal until an editor and a lawyer are in place. Public = facts + attributed claims.
4. **Buyers are organisations**: corporate public-affairs / government-relations teams and PR
   agencies (highest willingness to pay), policy consultancies, newsrooms. Journalists are the
   distribution channel. Citizens and UPSC aspirants bring traffic, not revenue. Political
   campaign war rooms pay but would destroy neutrality — don't sell to them publicly.
5. **Prove payment before building more.**

## Comparables (from the investor review)

- **FiscalNote** — the category's venture bet: $1.3B SPAC (2021) → NYSE-delisted Apr 2026, ~$3M
  market cap, under debt forbearance. Data roll-ups at venture valuations did not create a moat.
- **Quorum** — bootstrapped since 2014, ~$61M revenue: won on *workflow* (stakeholder CRM,
  advocacy) sold per seat.
- **Politico Pro** — journalism layered on data, ~5,000 high-price subscriptions.
- **India** — PRS (philanthropic; FCRA-blocked foreign funding), CivicDataLab (grants), SCC
  Online / Manupatra (legal duopoly, seats), PolicyRadar / Policy Index (policy aggregation). No
  funded Indian parliamentary/policy-intelligence SaaS found.

## Moat — what is and isn't defensible

- **Replicable in ~3 months**: scrapers, English PDF parsing, chunked search, YouTube captions,
  AI digests.
- **Defensible, in order**: (1) entity-resolved identity graph over time across sources;
  (2) evidence-graded issue timelines *once there's an editorial track record*; (3) regional-
  language depth *if* the hard parts get done (Hindi PDF extraction, state assemblies);
  (4) brand/distribution with newsrooms (none yet).
- Keeping `sansad.db` private does not by itself protect anything — the source data is public.
  The moat is curation and linking.

## Risks

Political/regulatory (IT Rules 2026: 3-hour takedowns; Sahyog portal), defamation, source
dependence (eparlib needs a browser; YouTube 429s caption downloads per IP and its ToS prohibits
automated access; X API is paid), solo-founder bandwidth, low willingness to pay. Trust: one viral
misattribution or bad Hindi translation ends the brand → always show original beside translation,
one-click source, public corrections log.

## Recommended path (synthesis)

The hidden-connections vision is the **long-term asset**, not the **first thing to sell or
publish**. Build the graph behind a product people pay for now.

| Stage | Build | Proof / gate |
|---|---|---|
| **Now → 6 weeks** | Person/topic **alerts + daily brief** (email/WhatsApp); **quote cards** with permalink + source + party-on-date; **dossier export** ("everything X said on Manipur"); methodology + corrections page | — |
| **Public showcase** | 3–5 timelines, **facts + claims only** (CJP → Pradhan resignation first) | Organic sharing during news cycles |
| **Day 90 go/no-go** | Paid pilots: 3 GR/PR teams or newsrooms at ₹25–50k/month | ≥ 2 pilots signed, ≥ 20 weekly active journalists, quote cards cited in published stories |
| **G1 (6–9 mo)** | + Rajya Sabha, 2 state assemblies, working Hindi extraction | 5 paying orgs (~₹25–40 L ARR) → angels / pre-seed |
| **G2 (12–18 mo)** | API / data licensing; editor co-founder | ₹1.5–3 cr ARR, NRR > 100% → seed |

**Stop / pivot signals:** by day 90 fewer than 10 weekly journalists *and* no paid pilot; Sansad
Bhashini ships good cross-language debate search (leaving YouTube as the only edge); a legal
notice before any revenue. Fallback: B2B data licensing (research, GR) instead of a public brand.

**Non-dilutive money:** IPSMF, Google News Initiative, data.org / foundations, IndiaAI / Startup
India — expect strict non-partisanship and open-data strings (may conflict with the private
dataset); foreign money triggers FCRA scrutiny. Prefer Indian-sourced grants; publish a neutrality
methodology.

## Open decisions (founder)

1. First paid product: alerts/brief (investor) vs public quote search + cards (marketing) — or both,
   with cards as the free funnel into alerts.
2. Target first design partner: which newsroom / GR team / PR agency.
3. Editorial co-founder or advisor — who, and before or after the first public timeline.
4. Timelines: free public showcase vs part of the paid product.
5. YouTube: ToS risk vs value — keep low-volume/non-commercial until there's a licence/API path?
