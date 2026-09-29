# ParamaSrota — Story Engine (concept v1)

*Written 2026-09-29. Supersedes the "pivot" discussion; builds on `PROJECT_BRIEF.md`,
`PRODUCT_STRATEGY.md` and `ISSUE_TIMELINES.md`. Read this before any product, content or UI work.*

> **ParamaSrota explains how India got here — one question at a time — as a clear timeline of the
> decisions that made it happen, built on a public, sourced record that gets stronger with every story.**

---

## 1. Three layers, one engine

| Layer | What it is | Role |
|---|---|---|
| **Story** | Blog post answering one question with a live news hook ("Why does India suddenly produce chess champions?"). 5-minute read, one chart. | Brings readers in |
| **Map** | Interactive timeline behind each story. Every node typed, weighted, graded. | Makes it understandable |
| **Record** | Wiki: one page per person, organisation, policy, event, quote (Parliament, SEBI, PIB, NGO…), each linked to its original source. | **The asset.** Outlives any story |

Stories are built *on* the Record. Every story must add to it and reuse it.

The existing parliament / PIB / YouTube pipelines become **source feeds into the Record**, not
products of their own.

## 2. Decision taxonomy (every Map node gets exactly one role)

| Role | Meaning | Example |
|---|---|---|
| **Deliberate bet** | Chosen by someone aiming at this outcome | A state creates a dedicated IT park |
| **Spillover** | Chosen for another reason; helped via network effects | Cheap mobile data → online chess |
| **Unblocker** | Removed an obstacle | — |
| **Roadblock** | Delayed or prevented the outcome (incl. good decisions with side effects) | — |
| **Wildcard** | Not a decision — a shock or a person | COVID lockdowns; one prodigy's win |

Each node also carries:

- **Weight** — essential / accelerant / minor
- **Evidence grade** — confirmed / reported / claimed, by count of *independent* sources
  (same rules as `ISSUE_TIMELINES.md`: re-uploads of one source count once)
- **Counterfactual note** — would the outcome have happened without it? Answered with
  **comparison cases** (why Hyderabad and not Chennai?). A precondition present in both places
  didn't cause the difference.

### Node schema (starting point)

```
node_id, story_ids[], date, date_precision (day|month|year|approx),
actor_id (→ Record), decision_text, role, intent_toward_outcome (bool),
weight, evidence_grade, source_ids[] (→ Record), counterfactual_note,
comparison_case (optional)
```

Edges: `node → node` with `relation` (enabled | accelerated | blocked | triggered) and its own
evidence grade. The structure is a directed graph, not a tree.

## 3. Editorial rules for every new post

1. **Live hook** — ties to something currently viral or nationally relevant (check the news
   cycle before publishing).
2. **Reuse** — links ≥ 1 existing Record page, ideally ≥ 3.
3. **Upgrade** — adds ≥ 1 new independent source that strengthens an existing node.
4. **Rotate pillars** — politics → sports → business.
5. **Facts and claims only in public.** Hypotheses stay internal.

## 4. The Record (wiki) — surface it now, quietly

**Decision:** yes, publish the Record from day one, but as a supporting layer, not a destination.

- **Publish gate:** a Record page goes public only when a published story cites it *and* it has
  ≥ 1 source link + an evidence grade. Everything else stays private as a stub.
- **Discovery:** no top-nav slot. Reached via inline links in stories (footnote-style) and a small
  "Record" link in the footer.
- **Show reuse on the page:** "Cited in N stories", listing them. This makes reuse visible to
  readers and is the metric in one glance.
- **Index it.** Record pages are the long-tail search traffic ("Viswanathan Anand", "Cyberabad
  policy"). Quiet in navigation, loud to Google.
- **Promote to a destination later**, when ~50 public pages exist and several are cited 3+ times.

## 5. Metrics

- **North star: reuse ratio** — share of a new story's nodes that already existed in the Record.
  Rising post after post = the platform thesis is working. Flat = it's a good blog, not a platform.
- **Build-cost trend** — is story #3 cheaper to make than story #1?
- **Record pages cited 2+ times**, and evidence-grade upgrades per post.
- Story: shares and time on page.

## 6. Starter set

| Pillar | Question | Why first |
|---|---|---|
| Sports | What came together for India's chess boom? | Rich in wildcards and spillovers; well documented |
| Business | What came together for Hyderabad IT? | Clear deliberate bets; sets up Bain-style India data later |
| Politics | Women's Reservation Act (2023) — after ~27 years of failed attempts, what changed? | Roadblocks/unblockers; built on parliamentary quotes, so existing sansad data plugs in |

Confirm each hook against the current news cycle before publishing.

## 7. What this is not

- **Not breaking news** — it explains, it doesn't report.
- **Not opinion** — every claim graded and sourced.
- **Not a data platform yet** — that comes when the reuse ratio says so.

## 8. Open questions (next iteration)

1. Map UI — the rejected timeline prototype is still the crux; start fresh from the taxonomy above.
2. Record page template per entity type (person / org / policy / event / quote).
3. Storage: Record + nodes in the existing SQLite schema, or a separate graph table set?
4. Editorial advisor — still the missing role (see `PRODUCT_STRATEGY.md`).
5. Cadence — one story every 2 weeks is the realistic solo pace to test.
