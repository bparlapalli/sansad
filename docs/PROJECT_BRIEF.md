# ParamaSrota — project brief

*For product, marketing, strategy and UI conversations. Written 2026-09-28. Technical detail
lives in `CLAUDE.md`; this document is the non-technical baseline.*

> **परम श्रोता — "The Supreme Listener."** What India's political leaders actually said —
> in Parliament, at press conferences, in official releases — searchable, sourced to the page or
> the second, in Hindi and English, and connected across issues over time.

---

## 1. The idea in one paragraph

Indian political speech is scattered: Lok Sabha debates are long Hindi/English PDFs, press
conferences are hour-long YouTube livestreams, government statements are press releases.
ParamaSrota collects them, attributes every statement to a person, tags it with the party that
person belonged to **on that day** (leaders switch parties; their history shouldn't), and makes it
searchable down to the paragraph or video second. The longer-term vision is **issue timelines**:
one page per political issue (Manipur, a protest movement, a plant closure) that layers dated,
evidence-graded data points and reveals connections between issues through the people, places and
events they share.

## 2. Current state (honest)

| Area | Status |
|---|---|
| **Parliament** (Lok Sabha debates) | 3,073 attributed statements, 54,526 searchable paragraph-sized chunks, 401 members. Coverage Aug 2025 → Feb 2026 only — most of the 18th Lok Sabha isn't downloaded yet. Hindi PDFs parse poorly. |
| **PIB** (government press releases) | Working; 346 releases (one week, 21–27 Sep 2026) — history not backfilled. |
| **YouTube** (party & leader channels) | Built. 1,245 videos from the last 30 days indexed (INC, BJP, Rahul Gandhi, Priyanka Gandhi, Modi, Amit Shah, CJP's Abhijeet Dipke via news channels). **0 transcripts so far** — YouTube is rate-limiting caption downloads from our IP. |
| **People & parties** | 12 tracked leaders with dated party history (e.g. Scindia: INC → BJP 2020). |
| **Search / feed / topic pages** | Live. Search shows the matching paragraph, not a wall of text. |
| **AI digests & MP profiles** | Built, but none generated yet (no API key set). |
| **Issue timelines** | Concept agreed; research data for 3 issues (114 public data points); **UI prototype rejected** — needs a fresh design. |
| **Live site** | https://sansad-b039.onrender.com — unlisted, free hosting, shows a rolling 30-day window. The full dataset stays on the founder's machine by design. |
| **Team / money** | Solo founder. No revenue, no funding. |

## 3. What the market reviews said (summary of `PRODUCT_STRATEGY.md`)

Two skeptical reviews — a product-marketing manager and a seed investor — reached nearly the same
conclusion:

- **The product is "the receipts"**: sourced, timestamped, party-dated quotes across Parliament +
  YouTube + official releases, in Hindi and English. Nobody does this for Indian politicians.
- **Plain Parliament search is not a moat** — the government's own portals (sansad.in, Sansad
  Bhashini) are commoditising it.
- **The "hidden connections" map is the long-term asset but the biggest legal risk** (criminal
  defamation exists in India). Public = facts + attributed claims only; hypotheses stay internal.
- **Buyers are organisations** — corporate government-relations teams and PR agencies (highest
  willingness to pay), policy consultancies, newsrooms. Journalists are distribution. Citizens bring
  traffic, not revenue. Don't sell to political campaigns publicly.
- **Marketing verdict:** worth pursuing as a receipts engine. **Investor verdict:** watch — prove
  someone pays. It's a solid lifestyle-scale business (~₹70 cr serviceable market); venture scale
  only if it widens to regulatory and corporate intelligence — SEBI/RBI/CCI orders, exchange
  filings, PSUs and DPSUs, CAG audits, Gazette, clearances, tenders, electoral bonds — joined on
  company and director IDs. Catalogue and order: `DATA_SOURCES.md`.
- **Cautionary comparable:** FiscalNote (US political data) went from a $1.3B valuation (2021) to
  delisted (2026). Quorum succeeded bootstrapped by selling workflow tools per seat.

### Recommended path
1. **Next ~6 weeks:** person/topic **alerts + daily brief** (email/WhatsApp), **quote cards**
   (shareable, permalinked, sourced), **dossier export**, a **methodology + corrections page**.
2. **Public showcase:** 3–5 issue timelines, facts + claims only.
3. **Day-90 test:** ≥ 2 paid pilots (₹25–50k/month) with GR/PR teams or newsrooms; ≥ 20 weekly
   active journalists. **Stop/pivot** if none — or if government search catches up, or a legal
   notice arrives before revenue.

## 4. Issue timelines — the idea

(Full concept: `ISSUE_TIMELINES.md`. UI directions: `TIMELINE_UI_IDEAS.md`.)

- One page per issue; data points on a time axis, grouped into **facets** (government, Parliament,
  courts, protest, security, party politics, international, online).
- **Three layers, never mixed:** **facts** (graded confirmed / reported / disputed), **claims**
  ("the minister *said* X" — the statement is certain, its content may not be), and
  **hypotheses** (proposed hidden links, internal only).
- **Certainty comes from independent sources**, not age. Ten channels re-uploading one press
  conference count as one source. As new sources are added, points upgrade automatically.
- **Everything is a node** — people, parties, places, organisations, statements, actions — so issues
  connect through what they share. An event can belong to several issues.
- **Views:** issue page, a *lens* (one person/place/action across all issues), a connections map,
  and "how is X connected to Y?" paths where a chain is only as strong as its weakest link.
- **Why the layers matter — a real example:** a lead that "American agents were caught in Manipur"
  turned out to be a real NIA arrest of a US national and six Ukrainians (Myanmar drone-training
  allegation) with **no credible link to Manipur or the US government**. Without the layers it
  would have become a false "fact".

## 5. Decisions still open (tracked as GitHub issues #63–#68)

1. **First paid product** — private alerts/brief (investor) vs public quote search + shareable
   cards (marketing), or cards as a free funnel into paid alerts.
2. **Editorial owner** — both reviews say a journalist/editor co-founder or advisor is the missing
   role; timelines shouldn't go public without one.
3. **Timelines: free showcase or paid product?**
4. **YouTube risk** — its terms prohibit automated access; keep low-volume, switch to our own
   speech-to-text, or drop it for paid tiers?
5. **Timeline data model** — separate tables for facts / claims / hypotheses (recommended).
6. **First design partner** and the first 3 public issues (CJP → Education Minister's resignation
   is the best documented).

## 6. Questions worth discussing

**Product / marketing**
- Who exactly is the first customer — a named GR head, PR agency or newsroom desk? What would they
  pay for *this month*?
- What does the daily brief need to contain for a GR team to forward it to their CEO?
- How do we stay credibly neutral when tracking one party's leaders more than another's?
  (Symmetric coverage? Published methodology?)
- Name/brand: "ParamaSrota" in Hindi-first vs English-first markets?
- What content goes viral during a news cycle without becoming partisan?

**UI / design** (briefs: GitHub issues #58–#62)
- How should evidence levels look so a non-expert gets them in seconds — and screenshots keep them?
- Mobile-first timeline: vertical story vs horizontal lanes?
- How to show connections without a hairball or implying causation?
- Quote card design that journalists will actually embed.

## 7. Where things live

| What | Where |
|---|---|
| Code, docs, public timeline data | GitHub `bparlapalli/sansad` (public repo) |
| Strategy reviews | `docs/PRODUCT_STRATEGY.md` |
| Data expansion (SEBI, RBI, PSUs/DPSUs, CAG, tenders, electoral bonds…) | `docs/DATA_SOURCES.md` |
| Timeline concept + guardrails | `docs/ISSUE_TIMELINES.md` |
| Timeline UI directions | `docs/TIMELINE_UI_IDEAS.md` |
| Timeline data (facts + claims) | `docs/timelines/*.json` |
| Roadmap, UI briefs, decisions | GitHub issues (labels `ui-prototype`, `decision-needed`) |
| Full dataset, hypotheses | Founder's machine only |
