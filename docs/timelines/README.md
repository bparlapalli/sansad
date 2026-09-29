# Issue timelines — public edition

Concept and decisions: [`../ISSUE_TIMELINES.md`](../ISSUE_TIMELINES.md).

| File | What |
|---|---|
| `cjp-education-minister.json` | Cockroach Janta Party → Education Minister Dharmendra Pradhan's resignation (46 events) |
| `manipur.json` | Manipur conflict, May 2023 → Sep 2026 (44 events) |
| `sterlite-copper.json` | Sterlite Copper, Thoothukudi: protests, 2018 firing, closure, courts, copper trade (24 events + trade series) |
| `timeline.html` | Single-file prototype viewer (open from disk). **UI rejected — kept for reference; redesign needed.** |
| `build_public_edition.py` | Regenerates this folder from the local research edition (`data/timelines/`, gitignored) |

**This is the public edition**: confirmed / reported / disputed facts and *attributed* claims
only. Inferred events, inferred links and hypotheses exist only in the local research edition.
Do not hand-edit these files — edit the research edition and rerun the build script.

Researched 2026-09-28 by an AI research agent from web sources plus read-only queries of the
project DB; **not yet editorially reviewed**. Evidence levels for claims describe *that the
statement was made*; `content_evidence` says whether its content is verified.

## Verification notes

- **CJP / Pradhan** — well corroborated: CJI's 15 May remark, CJP launch 16 May, Pradhan's
  resignation 25 Jul, the task force and amendment bill, the CJP split (3 Sep), the CEC ultimatum
  (24 Sep). The *reason* for the resignation is `disputed` (moral grounds vs forced by protest),
  as are casualty accounts of 20 Jul. Much May–June material rests on single summaries → `reported`.
- **Manipur** — well covered to Feb 2026 by official sources (Biren Singh's resignation, President's
  Rule and its extension and revocation). Gaps: Supreme Court hearings 2024–25, talks, casualty
  tables, 2026 assembly sessions. A widely repeated claim linking the March 2026 NIA arrest of a
  US national and six Ukrainians (Myanmar drone-training allegation) to Manipur is **not supported
  by the charges as reported**; only the arrest and bail are recorded here, as facts.
- **Sterlite** — core facts multiply sourced (22 May 2018 firing: 13 dead; closure 28 May 2018;
  SC 2019/2024 rulings). Copper trade figures cite commerce-ministry data via press; two reports
  disagree on FY18 cathode imports (noted). FY20–23 series is a gap to fill from DGCI&S.
- **Vaishnaw remarks** (NDTV, 21 Sep 2026) are recorded as a **claim**: "food poisoning",
  "electricity wires were cut", "they tried all tricks" — no one named. The phrase "hidden forces"
  was not found in any report.
- Project data used: Parliament statements on Manipur (Dec 2025); PIB and YouTube data did not yet
  cover these issues (PIB window was one week; YouTube transcripts not yet fetched).
