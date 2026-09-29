# Issue timelines — UI ideas (baseline for design discussion)

*2026-09-28. Starting point for UI conversations and the `ui-prototype` GitHub issues (#58–#62).
Concept and rules: `ISSUE_TIMELINES.md`. Real data to design with: `docs/timelines/*.json`
(3 issues, 114 events, entities, cross-issue links, a trade series).*

> **The sketches below use illustrative mock content to show layout** — dates, labels and
> connections in them are placeholders, not verified data. Design with the JSON files for real
> content.

---

## 0. What the first prototype got wrong

`docs/timelines/timeline.html` proved the data model but was judged **not usable**. Likely
reasons, to avoid repeating:

- **Everything at once** — lanes, lens, paths, hypotheses, filters, legend and detail panel all on
  one screen. No obvious first thing to look at.
- **Horizontal swimlanes on a phone** — tiny markers, sideways scrolling, no pinch-zoom.
- **Markers without words** — solid/outline/dashed shapes mean nothing until you study a legend.
- **The story is missing** — a reader wants "what happened, in order, and why it matters"; the
  prototype showed a data structure.
- **Dense controls** — toggles and dropdowns before the reader knows what they're for.

**Design principle for v2:** *story first, structure on demand.* The default view tells the issue
as a readable sequence; lanes, lenses and connections are layers you open when you want them.

---

## 1. The reader's questions, in order

1. What is this issue, in two lines? Where does it stand today?
2. What happened, in order? (skim the 8–12 moments that matter)
3. How sure are we about each point, and where does it come from?
4. Who was involved, and what did each side say?
5. What else is this connected to?

Each view should answer these top-down; the deeper questions shouldn't clutter the first ones.

---

## 2. Issue page — three directions

### A. "Story" — vertical, mobile-first *(recommended starting point)*

```
┌──────────────────────────────┐
│ CJP → Education Minister     │
│ resigns                      │
│ Status: Pradhan resigned     │
│ 25 Jul; CJP split in Sep     │
│ [Key moments ▾] [All 46]     │
├──────────────────────────────┤
│ 2026                         │
│ ● 15 May  CONFIRMED  Courts  │
│   CJI calls unemployed youth │
│   "cockroaches"              │
│   ⌄ 2 sources                │
│ │                            │
│ ● 16 May  CONFIRMED  Protest │
│   Cockroach Janta Party      │
│   launched by Abhijeet Dipke │
│ │                            │
│ 💬 21 Jul  CLAIM             │
│   BJP: "anti-national forces"│
│   — said, not verified       │
│ │                            │
│ ◐ 20 Jul  DISPUTED           │
│   Casualties at protest —    │
│   police vs organisers       │
│ ...                          │
│ ↳ Also in: NEET paper leak   │
└──────────────────────────────┘
```

- One column, newest or oldest first (toggle). Each card: date (with "approx" when imprecise),
  a **word label** for evidence (CONFIRMED / REPORTED / DISPUTED / CLAIM), a facet tag, a
  one-line headline, expandable summary and sources.
- **"Key moments"** default: an editor-chosen 8–12 events; "All" shows everything.
- Facet chips at the top filter instead of lanes (Courts · Govt · Protest · Parliament…).
- Disputed items show both positions side by side when opened.
- Cross-issue links appear inline as a small "Also in: …" line on the event itself.
- **Pros:** readable by anyone, great on phones, screenshot-friendly.
  **Cons:** parallel activity across facets is harder to see.

### B. "Swimlanes" — horizontal, desktop analyst view

```
            May        Jun        Jul            Aug        Sep
Courts      ●──────────────────────●(HC order)
Govt                          ○────●(resigns)────●(task force)
Protest     ●(launch)──●───●──●●●(Jantar Mantar)───────●(split)
Parliament                         ●(bill)
Online      ●(IG growth)──●(X withheld)
─────────────────────────────────────────────────────────────
Connected   ◌ NEET leak           ◌ SIR/EC row
```

- Time on the x-axis, one lane per facet; zoom by year → month → week.
- Density strip above lanes shows where activity clusters.
- Best for analysts on a laptop; on phones fall back to Direction A.
- **Pros:** shows parallel pressure (protest ↔ government response) at a glance.
  **Cons:** needs space and a legend; this is where v1 failed on usability.

### C. "Chapters" — narrative blocks, then drill in

```
Chapter 1  The remark and the launch        (15–20 May)   5 events
Chapter 2  Street protests and the fast     (Jun–Jul)     12 events
Chapter 3  Resignation                      (25 Jul)       6 events
Chapter 4  Crackdown and courts             (Jul–Aug)      9 events
Chapter 5  The split and the EC row         (Sep)          7 events
```

- Issue split into editor-defined phases, each with a 2–3 line summary; tap a chapter to open
  its events (as Direction A cards).
- **Pros:** most "explainer-like"; good for sharing and for newcomers.
  **Cons:** needs editorial work per issue; phases are an interpretation.

**Suggested combination:** C's chapter summaries as section headers inside A on mobile; B as an
optional "analyst view" on desktop.

---

## 3. Evidence visual language (shared across every view)

Rule: **never rely on shape or colour alone — always a word.**

| Level | Label | Visual idea | Tooltip / expanded text |
|---|---|---|---|
| Confirmed | `CONFIRMED` | solid dot, strong colour | "Official record or ≥ 2 independent sources" |
| Reported | `REPORTED` | outline dot | "One credible source so far" |
| Disputed | `DISPUTED` | half-filled dot | "Sources disagree — see both sides" |
| Claim | `CLAIM` + speech bubble | quote styling, speaker name first | "X said this. That they said it is confirmed; whether it's true is *unverified / supported / refuted*" |
| Approx date | `~Jul 2026` | tilde / lighter date | "Exact date not known" |

- **Source-type badges** on each source line: `Parliament` `Court` `Gazette` `PIB` `Party channel`
  `News` — primary sources visually distinct.
- Colour-blind and greyscale safe; must survive a screenshot on WhatsApp/X without the page
  around it (label text is inside the card, not only in a legend).
- **Internal-only** (never in public UI): inferred items and hypotheses — dashed, watermarked
  "working hypothesis".

---

## 4. Connections

### Lens — "everything about X"
Pick a person, place, organisation or action type:
```
Jantar Mantar
  CJP issue       ● 20 Jul protest   ● 26 Jul rally
  Manipur         ● 2023 solidarity sit-in
  Wrestlers       ● 2023 protest
```
One row/section per issue, the entity's **role** shown on each point (spoke, ordered, arrested,
protested). Entry points: tap any name on an event card.

### Connections map
- Issues = large circles; shared entities = small dots between them; line thickness = overlap.
- **Hub entities hidden by default** (BJP, INC, Government of India, Delhi, Supreme Court) with a
  toggle — otherwise everything connects to everything.
- A time slider replays how issues started touching.
- On mobile, replace the graph with a ranked list: "Manipur shares 4 people and 2 places with …".

### Path — "how is X connected to Y?"
```
Dipke ──protested at──▶ Jantar Mantar ──site of──▶ Manipur solidarity sit-in (2023)
       CONFIRMED                       CONFIRMED
Strength: CONFIRMED (weakest link)
```
Each hop labelled with its relation and evidence; the chain's strength = its weakest hop. Never
phrase a path as causation; wording is "connected through".

---

## 5. Supporting surfaces

- **Series overlay** (e.g. copper imports under the Sterlite timeline): a small chart with event
  pins; caption always says "correlation, not cause".
- **Quote card** (shareable): verbatim quote (original + English), speaker, party *on that date*,
  date, source badge, permalink, ParamaSrota mark. Designed for a WhatsApp/X screenshot.
- **Daily brief** (paid product): "Your watchlist today" — per person/issue, 3–5 items, each a
  quote card in miniature with a source link; one-tap "open timeline".
- **Corrections & methodology** link visible on every timeline page.

---

## 6. Open UI questions

1. Default ordering: chronological (oldest first) or "latest first with a recap"?
2. Who picks "key moments" — editor, or a rule (confirmed + most-linked)?
3. Does the swimlane view earn its complexity, or is Story + Lens enough for launch?
4. How do disputed items show both sides without taking a side visually?
5. How to show "updated since your last visit" when points are upgraded or added?
6. How much of the connections map is useful to non-analysts?

## 7. How to evaluate a direction

- A first-time reader on a phone can say **what happened and how sure we are** within 30 seconds.
- Every point is **one tap from its source**.
- A screenshot of any card **keeps its meaning** (evidence label + source visible).
- Claims can never be mistaken for facts.
- Works with the real JSON (46 events for CJP) without feeling crowded.
