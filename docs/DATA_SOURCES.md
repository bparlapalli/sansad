# Data sources — current and expansion catalogue

*2026-09-28. Why this matters: the investor review found the parliament-and-politicians market
alone is lifestyle-scale (~₹70 cr). It becomes venture-scale if ParamaSrota widens into
**regulatory and corporate intelligence** — who regulates, funds, contracts with and litigates
against whom — sold to compliance teams, corporates, funds and foreign investors. Everything below
is **public**. Access notes are from general knowledge and must be checked source-by-source before
building (terms of use, captchas, rate limits).*

---

## 1. The idea: an identity spine that joins everything

Each source on its own is a commodity. The value is in **joining them on stable IDs**:

| Entity | Stable ID | Appears in |
|---|---|---|
| Politician | our `people.slug` (+ ECI candidate record) | Parliament, YouTube, PIB, ECI affidavits, ministries held |
| Company | **CIN** (MCA), ISIN / scrip code (exchanges) | MCA, SEBI orders, exchange filings, tenders, electoral bonds, CCI, NCLT/IBBI, clearances |
| Director / promoter | **DIN** (MCA) | MCA, exchange filings, SEBI orders |
| PSU / DPSU | CIN + ministry | DPE survey, CAG, exchange filings, tenders, DAC approvals |
| Regulator / ministry | our entity id | orders, circulars, gazette, Parliament answers |
| Place / project | project id (clearance, tender) | PARIVESH, tenders, courts |

Example of the kind of question this answers (as **facts**, each sourced — never as an implied
wrongdoing): *"Company X — its SEBI orders, the tenders it won, the environmental clearances it got,
its electoral-bond purchases, what ministers said about its sector in Parliament, and when."*

**Guardrail:** joins are presented as dated, sourced facts. Anything implying motive or
impropriety is a *hypothesis* and stays internal (see `ISSUE_TIMELINES.md` §7).

---

## 2. Already built

| Source | What | State |
|---|---|---|
| Lok Sabha debates (eparlib / sansad.in) | Attributed statements | Partial coverage; Hindi weak |
| PIB press releases | Government statements, Cabinet decisions, DAC approvals | One week; needs backfill |
| YouTube (party & leader channels) | Press conferences, speeches | Listed, transcripts blocked |

---

## 3. Markets & financial regulators

| Source | What you get | Value / who pays | Access (verify) | Tier |
|---|---|---|---|---|
| **SEBI** — enforcement & adjudication orders, settlement orders, circulars, consultation papers, board-meeting outcomes | Who was penalised/barred, for what, when; regulatory direction | Compliance, funds, law firms, journalists | Public pages + PDFs | **1** |
| **Stock exchange filings** (BSE, NSE) — corporate announcements, board outcomes, shareholding patterns, related-party transactions, insider/SAST disclosures, credit-rating actions | Corporate events for every listed company incl. listed PSUs/DPSUs | Funds, analysts, GR teams | BSE relatively open; NSE blocks bots (browser needed) | **1** |
| **RBI** — press releases, **penalties on banks/NBFCs**, notifications, master directions, MPC minutes, DBIE statistics | Banking regulation and enforcement | Banks, fintech, funds | Public | **1** |
| **IRDAI**, **PFRDA** | Insurance / pension orders and circulars | Insurers, compliance | Public | 2 |
| **IFSCA** (GIFT City) | Regulations, approvals | Funds, fintech | Public | 3 |

## 4. Sector regulators & approvals

| Source | What you get | Tier |
|---|---|---|
| **CCI** — competition orders, merger approvals | Who is combining/being investigated | **1** |
| **TRAI** — consultation papers **with stakeholder comments** | Which companies argued what, on record — the closest India has to lobbying disclosure | **1** |
| **PARIVESH** (MoEFCC) — environmental, forest, wildlife, CRZ clearances | Project approvals with company, location, date — ties directly to issues like Sterlite | **1** |
| CERC / state ERCs — tariff orders | Power sector | 2 |
| **CDSCO** — drug & device approvals; **FSSAI** — licences, recalls | Pharma / food | 2 |
| DGCA, PNGRB, AERA | Aviation, gas, airport tariffs | 3 |
| **NGT** orders | Environmental litigation | 2 |

## 5. Government companies — PSUs & DPSUs

| Source | What you get | Tier |
|---|---|---|
| **DPE Public Enterprises Survey** | Financials of all central public sector enterprises, year by year | **1** |
| **DIPAM** | Disinvestment, strategic sales, OFS, dividends | **1** |
| Listed CPSE filings (via exchanges) | Board changes, orders won, results — HAL, BEL, BHEL, NTPC, ONGC, Coal India, SAIL… | **1** (comes with exchange filings) |
| **DPSU** annual reports + order announcements (HAL, BEL, BEML, BDL, Mazagon Dock, GRSE, Cochin Shipyard, GSL, MIDHANI, AWEIL, Yantra, IOL…) | Defence production, exports, order books | **1** |
| **Defence Acquisition Council approvals** (via PIB), **positive indigenisation lists**, Srijan portal, defence export figures | What the state plans to buy, from whom, and indigenisation | **1** |
| **CAG audit reports** — incl. PSU and defence audits | Official findings of loss, delay, irregularity — primary-source "confirmed" material | **1** |
| Board-level appointments (Gazette, ACC decisions) | Who runs which PSU | 2 |

## 6. Money flows: procurement, budgets, funding

| Source | What you get | Tier |
|---|---|---|
| **GeM** (Government e-Marketplace) | Orders and sellers | 2 (partly public; heavy) |
| **CPPP / eprocure.gov.in**, defence procurement, state e-procurement portals | Tenders and **awards (who won what)** | 2 (captchas; state portals vary) |
| **Union Budget & Demands for Grants**, state budgets | Allocations by ministry/scheme | 2 |
| **Electoral bonds data** (published by ECI in 2024 after the Supreme Court struck the scheme down) | Which companies bought bonds and which parties encashed them, with dates | **1** — historical, one-off, high value when joined to tenders/orders |
| **Party contribution reports & audited accounts** (filed with ECI) | Declared donors above threshold | 2 |
| DPIIT FDI data, DGCI&S / TradeStat trade data | Investment and import/export series (the Sterlite copper chart) | 2 |

## 7. Legislature & executive (beyond debates)

| Source | What you get | Tier |
|---|---|---|
| **Parliament Questions** — starred & unstarred **answers** (Lok Sabha + Rajya Sabha) | Ministers' written answers with numbers — what the government officially says on every topic | **1** (same site as debates) |
| **Rajya Sabha debates** | Other half of Parliament | **1** |
| **Standing Committee & PAC reports** | Detailed scrutiny of ministries and PSUs | **1** |
| **Gazette of India** (eGazette) | Notifications, rules, appointments — the legal "it happened" record | **1** |
| State assembly debates | State politics; varies wildly by state | 3 |
| Cabinet decisions, ministry press releases | via PIB — already partly built | done |

## 8. Courts, insolvency & enforcement

| Source | What you get | Tier |
|---|---|---|
| **Supreme Court** judgments & daily orders | Final word on policy fights | 2 |
| **High Courts / eCourts / NJDG** | Case status by party name | 3 (captchas, scale) |
| **NCLT / NCLAT**, **IBBI** (CIRP announcements, liquidation) | Corporate insolvency — who's going under and who's buying | **1** |
| **ED, CBI, NIA, CVC** press releases | Enforcement actions announced by agencies (claims until adjudicated) | 2 |

## 9. Elections & people

| Source | What you get | Tier |
|---|---|---|
| **ECI candidate affidavits** (assets, liabilities, criminal cases, education) — also compiled by ADR / MyNeta | Politician profiles with verifiable declarations across elections | **1** (ADR data may need licensing/partnership) |
| ECI results (constituency level) | Who won where, margins | **1** |
| **MCA21** company & director master data (CIN, DIN, directorships) | Links politicians' families/associates to companies — handle with extreme care | 2 (partial free access; per-document fees) |

## 10. Media & public record

Sansad TV and DD News (YouTube), All India Radio news (newsonair), ministry and minister YouTube
channels, party websites (already planned), published RTI replies. Plus **data.gov.in** (Open
Government Data platform) as a catch-all for ministry datasets.

---

## 11. Suggested order (fits the recommended path)

The strategy says: prove a paid pilot first. Pick expansions that make the **first paid product**
(Leader & Issue Watch alerts) more valuable to government-relations and compliance buyers:

1. **Parliament Questions + Rajya Sabha** — same infrastructure as today; doubles political coverage.
2. **SEBI orders + RBI penalties + CCI orders** — small, regular, high-signal; a "regulatory watch"
   add-on to alerts. Ideal first expansion for compliance buyers.
3. **Exchange filings for listed PSUs/DPSUs + DAC approvals + CAG** — a "defence & PSU watch"
   vertical (clear buyers: defence suppliers, funds, consultancies).
4. **Gazette + PARIVESH + TRAI consultations** — policy-to-project trail.
5. **Electoral bonds + ECI affidavits + MCA** — the join layer; powerful, but the highest
   defamation sensitivity — only with an editor and legal review.
6. **Tenders, eCourts, state assemblies** — heavy scraping; later.

Each new source follows the existing pattern: scraper → table (+FTS) → register in
`core/sources.py` (so it appears in feed, topic pages and the miner) → public export →
`daily_update.py`. Companies need a new `companies` entity table keyed by CIN, parallel to `people`.

## 12. Open questions

- Which vertical first for revenue: regulatory watch (SEBI/RBI/CCI), defence & PSU watch, or
  policy-to-project (Gazette/PARIVESH)?
- Build vs partner for affidavit data (ADR/MyNeta) and company data (MCA-derived vendors).
- Legal review of the join layer before anything company↔politician is public.
- Storage: SQLite holds to a few GB; exchange filings + orders at scale point to Postgres (already
  on the roadmap).
