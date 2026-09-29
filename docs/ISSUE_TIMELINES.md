# Issue Timelines — concept, decisions, open questions

*Written 2026-09-28. Status: concept agreed; data model prototyped; **UI prototype rejected**
(see §8). Nothing here is in the Flask app or `sansad.db` yet.*

One page per political issue (Manipur; the Cockroach Janta Party → Education Minister's
resignation; the Sterlite copper closure → import dependence …). Dated data points are layered on
a timeline by facet, every point says how sure we are, and issues connect to each other through
the people, places, organisations and events they share — so that, as sources accumulate, links
nobody thought to look for become visible.

---

## 1. Three layers — never mixed

| Layer | Example | What is actually certain |
|---|---|---|
| **Fact** | Sterlite's Thoothukudi smelter was closed by the state on 28 May 2018 | Primary records / independent corroboration |
| **Claim** | A minister said Apple's India manufacturing faced "food poisoning" and cut wires | That *he said it* (video second / transcript) — **not** its content |
| **Hypothesis** | "The closure created import dependence that benefited foreign suppliers" | Nothing yet — a proposed link with evidence *for*, *against*, alternatives, and what would confirm it |

Claims carry `content_evidence`: unverified → supported → refuted, independently of the fact that
they were made. Hypotheses are an **internal working layer**; they are never published (see §7).

## 2. Evidence levels (facts)

- **confirmed** — primary record (gazette, court order, Parliament record, PIB, on-camera
  statement) or ≥ 2 *independent* credible outlets
- **reported** — one credible source, not yet corroborated
- **disputed** — credible sources conflict; both positions stored side by side
- **inferred** — our analytic link; must carry `reasoning` + `would_confirm`

Certainty comes from **source type, not age**. Every point also carries `date_precision`
(day / month / approx).

**Independence rule.** Ten channels uploading the same ANI feed or the same press conference are
*one* origin. Corroboration counts distinct origins, weighted: Parliament/court/gazette (primary) >
PIB/official statement (primary for *what the government said*) > a leader's own channel (primary
for *what they said*) > independent outlets (2+ confirm) > reposts/clips/social (leads only).
Evidence level is **computed from attached sources**, not hand-set, and every change is logged.

## 3. Linking model — everything is a node

| Node | Links by |
|---|---|
| People, parties, organisations | participation in events with a **role** (spoke, ordered, arrested, resigned, protested…); party membership is **dated** (same model as `affiliations` for party switchers) |
| Places | **nested** (Churachandpur → Manipur → India) so queries roll up |
| Talks (speech, press conference, PIB release, YouTube quote) | are **events** themselves, which **mention** other events/entities |
| Actions (arrest, resignation, court order, shutdown, deployment…) | typed `kind`, queryable across all issues |
| Events ↔ events | caused · responded_to · followed · contradicts · related — each link has its own evidence level |

**An event can belong to several issues** (Pradhan's resignation → CJP *and* NEET paper leak).
Shared events are the strongest cross-issue link; shared rare entities are next.

## 4. How links are shown (views to prototype)

1. **Issue page** — swimlanes by facet over a date axis; a bottom *connected* lane shows faded
   markers from other issues that share an entity/event, click to jump.
2. **Lens** — pick a person, place, organisation or action kind → one cross-issue timeline, one
   row per issue ("everything at Jantar Mantar", "every internet shutdown").
3. **Connections map** — issues as large nodes, shared entities as small ones, edge weight =
   overlap; a time slider shows when issues started touching.
4. **Path search** — "how is X connected to Y?" → chains of hops, each labelled with its evidence;
   **a chain is only as strong as its weakest hop** (one inferred hop → dashed chain).
5. **Series overlay** — official numbers (trade, production, FDI) charted under the lanes with
   events pinned on them; before/after is labelled *correlation*, never cause.

**Anti-hairball:** hub entities (BJP, INC, Govt of India, Delhi, Supreme Court…) are hidden or
down-weighted by default (compute it: IDF over event participation); rare shared entities are
highlighted.

## 5. Discovering hidden links (future features)

- **Claim extraction** over our statements, PIB and YouTube chunks: "foreign hand", "hidden
  forces", "anti-national forces", "sabotage", "conspiracy", "विदेशी ताकत", "विदेशी हाथ",
  "देश विरोधी ताकतें", "साज़िश" → `claim` candidates (speaker, party-on-date, sentence). Charting
  claim frequency by speaker/party/month turns anecdote into a series.
- **Co-occurrence** of non-hub entities across issues within a time window → suggested links
  (inferred, for review).
- **Beneficiary field** on events (who gained) — ask *cui bono* without asserting motive.
- **Event-pattern templates** (announcement → local protest → court stay → closure → imports
  rise) to find other issues with the same shape.

## 6. The mining loop

```
topic registry ──► miner runs each topic's queries over every source (core/sources.py search())
      ▲                                  │
      │                         candidate points (source row, snippet, date, entities)
      │                                  ▼
 new topics/entities ◄── review: attach to event / create event / reject (never auto-publish)
```

- Topic registry mirrors `core/party_registry.py`: per topic, English + Hindi queries, key
  entities, date range.
- Because every source already exposes `search()`, **each new source feeds every topic
  automatically**; more independent sources → more points reach *confirmed*.

## 7. Guardrails (agreed)

- **Public = facts + attributed claims only.** Inferred events, inferred links and hypotheses stay
  in the local research edition (`data/timelines/`, gitignored). The public edition is generated by
  `docs/timelines/build_public_edition.py` with leak checks. India retains criminal defamation
  (BNS s.356); parliamentary-reporting protection doesn't cover our inferences.
- Every event needs ≥ 1 source; `date_precision` is always visible; claim markers permanently read
  "claim, not fact".
- Every hypothesis must list counter-evidence and alternatives (e.g. Sterlite: documented
  pollution/health complaints and 13 protesters killed are *facts* on the same timeline).
- No hypotheses naming private individuals. Keep a public corrections log.
- Example of why this matters: the "American agents in Manipur" lead turned out to be a real NIA
  arrest (US citizen + six Ukrainians, Mar 2026, Myanmar/Mizoram drone-training allegation) with
  **no credible link to Manipur or the US government** — it would have been a false fact without
  the layers.

## 8. Prototype status — UI rejected

`docs/timelines/timeline.html` (public edition) and `data/timelines/timeline.html` (research
edition, local) are a single-file prototype built to test the **data model**. Founder verdict
(2026-09-28): *"good in theory but the UI is really weak — it isn't usable or working in its
current form."* Keep the JSON schema; **redesign the UI from scratch**. Known gaps: no touch
pinch-zoom, not tested on a real phone, dense controls, lanes hard to read.

The data files are the useful part: 3 issues, 114 public events (inc. claims), entity overlap
across issues, a copper-trade series. Schema: `issue{slug,title,summary,lanes,edition}`,
`entities[{id,type,name,parent?,hub?}]`, `events[{id,date,date_precision,lane,kind,title,summary,
evidence,sources[],entities[{id,role}],issues[],links[],mentions[],claimant?,claim_text?,
content_evidence?}]`, `series[]`, (research edition only) `hypotheses[]`.

## 9. Decisions still open

1. **UI direction** for the issue page (vertical scroll story vs horizontal swimlanes vs hybrid;
   mobile-first?) — for UI prototype agents.
2. **Lens / connections map / path search** — which ships first, and how it looks on a phone.
3. **DB schema** — separate `events` / `claims` / `hypotheses` tables vs one table + type;
   reuse `people`/`parties`/`members` as entities (recommended).
4. **Review workflow** — who reviews candidate points, and where (`/admin/candidates`).
5. **Editorial owner** — both strategy reviews say a journalist/editor is the missing role;
   timelines shouldn't go public without one.
6. **Which issues first** — CJP → Pradhan resignation is the best-documented public showcase.
7. **Public vs paid** — are timelines free distribution (marketing view) or part of a paid
   product? See `docs/PRODUCT_STRATEGY.md`.
