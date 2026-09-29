"""
sync_github_issues.py — Keep GitHub issues in step with the roadmap. Idempotent.

Replaces the old create_github_issues.py (local-only, held a hardcoded token).
This file holds NO token. Auth, in order:
  1. GITHUB_PAT env var, or GITHUB_PAT=... in .env
  2. git's credential manager for github.com (the credential `git push` uses)

What it does (safe to rerun — every action is keyed and skipped if already done):
  CREATE   issues in NEW_ISSUES whose title doesn't exist yet
  COMMENT  on existing issues (COMMENTS) — each comment carries a hidden marker
  CLOSE    existing issues listed in CLOSE, with a closing comment

Usage:
    python sync_github_issues.py --dry-run
    python sync_github_issues.py
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
import requests

REPO = "bparlapalli/sansad"
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent
DOCS = "https://github.com/bparlapalli/sansad/blob/main/docs"

LABELS = {
    "status:done":     ("0e8a16", "Shipped — kept for the record"),
    "decision-needed": ("d93f0b", "Founder decision required before building"),
    "ui-prototype":    ("5319e7", "Open brief for UI agents: produce prototype ideas"),
    "youtube":         ("b60205", "YouTube party/leader source"),
    "timelines":       ("1d76db", "Issue timelines"),
    "product":         ("fbca04", "Product / go-to-market"),
    "data-quality":    ("c5def5", "Attribution, dedupe, translation"),
}

# ── Shared context pasted into UI briefs so each is self-contained ──────────
UI_CONTEXT = f"""
**Context for UI agents.** ParamaSrota is an Indian politics intelligence site (Flask + Jinja,
SQLite). Read first: [`ISSUE_TIMELINES.md`]({DOCS}/ISSUE_TIMELINES.md) (concept, evidence
levels, linking model, guardrails) and [`PRODUCT_STRATEGY.md`]({DOCS}/PRODUCT_STRATEGY.md) (the
product is sourced, party-dated quotes; timelines are the public showcase).

**Data to design with:** [`docs/timelines/`]({DOCS}/timelines/) — three issues (CJP → Pradhan
resignation, Manipur, Sterlite copper), 114 events with lanes, evidence levels, entities with roles,
cross-issue links, claims, a trade series. Public edition: facts + attributed claims only.

**Non-negotiables:** evidence level visible on every point (confirmed / reported / disputed, plus
claim vs fact); date precision visible; every point one tap from its source; works on a phone
(most Indian users are mobile); readable by a non-expert in 10 seconds. The existing
`docs/timelines/timeline.html` was **rejected as unusable** — don't iterate on it; start fresh.

**Deliverable:** 2–3 distinct directions (sketch/mock or clickable HTML) with trade-offs, using the
real JSON, desktop + ~390px mobile.
"""

NEW_ISSUES = [
    # ── Done (created closed, for the record) ──────────────────────────────
    dict(key="done-youtube", closed=True, labels=["status:done", "youtube", "scraper"],
         title="[Done] YouTube party & leader source (INC, BJP, CJP)",
         body="""Shipped 2026-09-28 (commit 7492607).
- `core/party_registry.py`: parties, people, dated affiliations, verified accounts
  (@IndianNationalCongress, @bjp, @RahulGandhi, @PriyankaGandhi, @narendramodi, @AmitShah;
  CJP/Abhijeet Dipke via search — no official channel). Impostor handles noted (@INCIndia).
- `scrapers/youtube/youtube_scraper.py`: walks /streams (press conferences are livestreams) and
  /videos with yt-dlp; attributes speaker (owner channel or title match); captions → ~60-word
  timed quote chunks that deep-link to the second.
- Tables: parties, people, affiliations, source_accounts, media_items, media_chunks (+FTS).
- Wired into /feed, /t/<topic>, export_public_db, daily_update.
- 1,245 videos listed for the last 30 days; caption fetch blocked by YouTube rate limit (see backfill issue)."""),
    dict(key="done-affiliations", closed=True, labels=["status:done", "database"],
         title="[Done] Party switching: dated affiliations — quotes tagged with party on the day",
         body="""A person has one identity for life; party membership lives only in `affiliations`
(person, party, role, start_date, end_date). Each quote gets `party_on(person, date)`.
Worked example: Jyotiraditya Scindia (INC until 2020-03-10, BJP from 2020-03-11)."""),
    dict(key="done-timeline-concept", closed=True, labels=["status:done", "timelines"],
         title="[Done] Issue-timeline concept + research data for 3 issues",
         body=f"""See [`ISSUE_TIMELINES.md`]({DOCS}/ISSUE_TIMELINES.md) and
[`docs/timelines/`]({DOCS}/timelines/). Fact / attributed-claim / internal-hypothesis layers;
evidence computed from independent sources; everything-is-a-node linking. Public edition (facts +
claims) committed; research edition with hypotheses kept local in gitignored `data/`.
UI prototype rejected — see the UI prototype issues."""),
    dict(key="done-strategy", closed=True, labels=["status:done", "product", "documentation"],
         title="[Done] Product strategy review (marketing + investor)",
         body=f"""See [`PRODUCT_STRATEGY.md`]({DOCS}/PRODUCT_STRATEGY.md). Both reviews: the product is
sourced, party-dated quotes + alerts; hidden links stay internal; prove a paid pilot by day 90."""),

    # ── Build next ──────────────────────────────────────────────────────────
    dict(key="yt-backfill", labels=["youtube", "priority:high"],
         title="YouTube caption backfill — 1,245 listed videos, blocked by rate limit",
         body="""YouTube returns HTTP 429 on caption downloads from this IP (since 2026-09-28).
`python scrapers/youtube/youtube_scraper.py --fetch-only --days 30` resumes; fetch order is
press conferences first, then longest videos.
- [ ] Rerun after the block clears; if it persists, add `--cookies-from-browser firefox`
- [ ] Consider `--english` (YouTube machine translation into `media_chunks.text_en`, 2× requests)
- [ ] Note YouTube ToS risk (see decision issue)"""),
    dict(key="alerts", labels=["product", "priority:high"],
         title="Leader & Issue Watch: alerts + daily brief (first paid product)",
         body=f"""Both strategy reviews' first product. User picks ~20 politicians + ~5 issues → daily
email/WhatsApp brief; each item = quote, source link (PDF page / video second / PIB), party on
that date, evidence label. Plus instant alerts on keywords. Target: 3 paid pilots at ₹25–50k/month
by day 90. See [`PRODUCT_STRATEGY.md`]({DOCS}/PRODUCT_STRATEGY.md). Related: #29."""),
    dict(key="dossier", labels=["product", "priority:medium"],
         title="Dossier export: everything X said on topic Y (PDF/CSV)",
         body="""Across Parliament statements, YouTube quotes and PIB: filter by person + topic + date range,
export with sources and party-on-date. Part of the Leader & Issue Watch offer."""),
    dict(key="methodology", labels=["product", "documentation", "priority:high"],
         title="Methodology + corrections page",
         body="""Public page: sources, how attribution works (owner channel / title match / search), evidence
levels, party-on-date, what we don't do (no hypotheses published), and a corrections log.
Both reviews call this a prerequisite for trust and political neutrality."""),
    dict(key="timeline-db", labels=["timelines", "database", "priority:medium"],
         title="Timelines: DB tables + /issues/<slug> blueprint",
         body=f"""After the UI direction is chosen. Proposed in [`ISSUE_TIMELINES.md`]({DOCS}/ISSUE_TIMELINES.md) §8
and the research notes: issues, events, event_issues, event_entities(role), event_links,
event_sources (pointing at statement_chunks / pib_releases / media_chunks rows), claims,
hypotheses (internal), series. Reuse people/parties/members as entities. `visibility` column
drives the public export."""),
    dict(key="miner", labels=["timelines", "intelligence", "priority:medium"],
         title="Topic registry + miner + candidate review queue",
         body="""Topic registry (like party_registry.py): English + Hindi queries, key entities, date range.
Nightly miner runs each topic over every source's `search()` → `candidate_events`; review at
`/admin/candidates` (attach / create / reject; never auto-publish). Evidence computed from
independent origins (ten channels re-uploading one press conference = one origin)."""),
    dict(key="claims", labels=["intelligence", "priority:medium"],
         title="Claim extraction: 'foreign hand', 'hidden forces', 'विदेशी ताकत'…",
         body="""Pattern rules over statements, PIB and YouTube chunks → `claim` candidates (speaker,
party-on-date, sentence, nearest referent), `content_evidence = unverified`. Chart claim
frequency by speaker/party/month. Related: #23."""),
    dict(key="yt-dedupe", labels=["youtube", "data-quality"],
         title="Dedupe the same press conference uploaded by several channels",
         body="""Dipke's press conferences appear on many news channels. Group by date + title similarity
(+ transcript overlap once fetched) into one origin; needed for the independence rule."""),
    dict(key="yt-attribution", labels=["youtube", "data-quality"],
         title="Per-speaker attribution inside multi-speaker press conferences",
         body="""Today a party-channel video is credited to the leader named first in its title. Press
briefings have several speakers. Options: speaker cues in the transcript ("मैं … कहना चाहता हूँ"),
description parsing, diarisation."""),
    dict(key="party-sites", labels=["scraper", "priority:medium"],
         title="Party website press-release scrapers (inc.in, bjp.org, cockroachjantaparty.org)",
         body="""Next-easiest source after YouTube: plain HTML, same pattern as PIB. Accounts already in
`core/party_registry.py` with active=0 — verify URLs first."""),
    dict(key="person-page", labels=["ui", "priority:medium"],
         title="Person page: Parliament statements + YouTube quotes + affiliations timeline",
         body="""`/person/<slug>` joining `people.member_id` → statements, media_items, affiliations
(showing party switches). Related: #8."""),

    # ── UI prototype briefs ─────────────────────────────────────────────────
    dict(key="ui-issue-page", labels=["ui-prototype", "timelines", "ui"],
         title="UI prototype: Issue timeline page (redesign — current prototype rejected)",
         body="""Design the page for one issue (start with CJP → Pradhan resignation). Explore at least:
a vertical scroll "story" timeline, horizontal facet swimlanes, and a hybrid (story on mobile,
lanes on desktop). Must show lanes/facets, evidence level, claim vs fact, date precision, sources,
and a lightweight "also connected to …" for other issues.
""" + UI_CONTEXT),
    dict(key="ui-lens", labels=["ui-prototype", "timelines", "ui"],
         title="UI prototype: Lens — one person/place/action across all issues",
         body="""Pick an entity (a person, a place like Jantar Mantar, an organisation) or an action kind
(arrests, internet shutdowns) → one cross-issue timeline, one row/section per issue. Show roles
(spoke, ordered, arrested…) and let users hop to the issue page.
""" + UI_CONTEXT),
    dict(key="ui-connections", labels=["ui-prototype", "timelines", "ui"],
         title="UI prototype: Connections map + 'how is X connected to Y' path view",
         body="""Issues as large nodes, shared entities as small nodes, edge weight = overlap; time slider.
Path view: chains of hops each labelled with evidence; a chain is as strong as its weakest hop.
Hub entities (BJP, INC, Govt of India, Delhi) hidden by default. Must not become a hairball, and
must not make co-occurrence look like causation.
""" + UI_CONTEXT),
    dict(key="ui-evidence-language", labels=["ui-prototype", "ui"],
         title="UI prototype: visual language for evidence levels, claims and date precision",
         body="""One shared system used by every view: confirmed / reported / disputed (facts), attributed
claim (with content verified / unverified / refuted), approx vs exact dates, source-type badges
(Parliament, court, PIB, party channel, news). Needs to work in colour-blind and greyscale modes
and survive being screenshotted onto social media without losing its meaning.
""" + UI_CONTEXT),
    dict(key="ui-brief", labels=["ui-prototype", "product", "ui"],
         title="UI prototype: daily brief email / WhatsApp format + watchlist setup",
         body="""For the Leader & Issue Watch product: the daily brief layout (email + WhatsApp message),
and the onboarding flow to pick politicians and issues. Each item: quote (original + English),
speaker, party on date, source link, evidence label.
""" + UI_CONTEXT),

    # ── Decisions ───────────────────────────────────────────────────────────
    dict(key="dec-first-product", labels=["decision-needed", "product"],
         title="Decision: first paid product — alerts/brief vs public quote search + cards",
         body=f"""Investor: private Leader & Issue Watch. Marketing: public quote search + shareable cards,
timelines as distribution. Possible: cards as free funnel into paid alerts.
[`PRODUCT_STRATEGY.md`]({DOCS}/PRODUCT_STRATEGY.md)"""),
    dict(key="dec-editor", labels=["decision-needed", "product"],
         title="Decision: editorial co-founder / advisor before timelines go public",
         body="""Both reviews name a journalist/editor as the missing role; timelines and claim labelling need
an editorial owner and a legal review path before public launch."""),
    dict(key="dec-timelines-public", labels=["decision-needed", "timelines"],
         title="Decision: timelines — free public showcase or part of the paid product?",
         body="""Marketing: free, shareable during news cycles (distribution). Investor: the evidence graph is
the moat. Hypotheses stay internal either way."""),
    dict(key="dec-youtube-tos", labels=["decision-needed", "youtube"],
         title="Decision: YouTube ToS posture (automated caption access)",
         body="""YouTube's ToS prohibits automated access without permission and rate-limits captions per IP.
Options: keep low-volume/non-commercial; official API for metadata + own ASR on audio; licensed
feeds (Sansad TV); drop YouTube for paid tiers."""),
    dict(key="dec-schema", labels=["decision-needed", "timelines", "database"],
         title="Decision: timeline schema — separate events/claims/hypotheses tables or one typed table",
         body=f"""Research notes recommend separate tables (claims have claimant + content status; hypotheses
are internal with supporting/counter events). See [`ISSUE_TIMELINES.md`]({DOCS}/ISSUE_TIMELINES.md) §9."""),
    dict(key="dec-partner", labels=["decision-needed", "product"],
         title="Decision: first design partner (newsroom / GR team / PR agency) and first 3 issues",
         body="""Pick one named design partner for weekly use, and the first public issues (CJP → Pradhan
resignation is the best documented)."""),
]

COMMENTS = {
    6:  ("yt-6", "Done in commit 7492607 — see the [Done] YouTube issue and "
                 "`scrapers/youtube/youtube_scraper.py`. Closing."),
    8:  ("aff-8", "Party affiliations over time now exist as `affiliations` (dated, per person) — "
                  "seeded manually in `core/party_registry.py`. ECI lookup would automate seeding."),
    23: ("claim-23", "Related: the new claim-extraction and issue-timeline work separates *that a claim "
                     "was made* from *whether its content holds* — see docs/ISSUE_TIMELINES.md."),
    29: ("alert-29", "Strategy review (docs/PRODUCT_STRATEGY.md) recommends alerts as the first paid "
                     "product — tracked in 'Leader & Issue Watch: alerts + daily brief'."),
    36: ("card-36", "Spec update from the strategy review: each card = verbatim quote (original + "
                    "English), speaker, **party on that date**, date, one-click source (PDF page / "
                    "video second / PIB), permalink. Positioned as the free funnel into alerts."),
}
CLOSE = {6}


# ── Plumbing ────────────────────────────────────────────────────────────────

def token():
    tok = os.getenv("GITHUB_PAT")
    env = ROOT / ".env"
    if not tok and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GITHUB_PAT="):
                tok = line.split("=", 1)[1].strip().strip('"')
    if not tok:
        out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                             capture_output=True, text=True, cwd=ROOT,
                             env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        tok = next((l[9:] for l in out.stdout.splitlines() if l.startswith("password=")), None)
    if not tok:
        sys.exit("No GitHub token: set GITHUB_PAT in the environment or .env")
    return tok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.github+json"})
    if not args.dry_run:
        s.headers["Authorization"] = f"Bearer {token()}"
        r = s.get(f"{API}/repos/{REPO}")
        if r.status_code != 200 or not r.json().get("permissions", {}).get("push"):
            sys.exit(f"Token can't write to {REPO} (HTTP {r.status_code})")

    existing, page = {}, 1
    while True:
        batch = s.get(f"{API}/repos/{REPO}/issues",
                      params={"state": "all", "per_page": 100, "page": page}).json()
        existing.update({i["title"]: i for i in batch if "pull_request" not in i})
        if len(batch) < 100:
            break
        page += 1
    have_labels = {l["name"] for l in s.get(f"{API}/repos/{REPO}/labels", params={"per_page": 100}).json()}

    def do(desc, method, url, **kw):
        print(("DRY " if args.dry_run else "") + desc)
        if args.dry_run:
            return None
        r = s.request(method, url, **kw)
        if r.status_code >= 300:
            print(f"   ERROR {r.status_code}: {r.text[:200]}")
        return r

    for name, (color, desc) in LABELS.items():
        if name not in have_labels:
            do(f"label   {name}", "POST", f"{API}/repos/{REPO}/labels",
               json={"name": name, "color": color, "description": desc})

    for it in NEW_ISSUES:
        if it["title"] in existing:
            print(f"skip    {it['title']}")
            continue
        r = do(f"create  {it['title']}", "POST", f"{API}/repos/{REPO}/issues",
               json={"title": it["title"], "body": it["body"], "labels": it["labels"]})
        if r is not None and r.status_code < 300:
            print(f"   #{r.json()['number']}")
            if it.get("closed"):
                do("   close", "PATCH", r.json()["url"], json={"state": "closed", "state_reason": "completed"})

    by_number = {i["number"]: i for i in existing.values()}
    for num, (key, text) in COMMENTS.items():
        marker = f"<!-- sync:{key} -->"
        if num not in by_number:
            continue
        comments = [] if args.dry_run else s.get(by_number[num]["comments_url"]).json()
        if any(marker in c.get("body", "") for c in comments):
            print(f"skip    comment #{num}")
            continue
        do(f"comment #{num}", "POST", by_number[num]["comments_url"], json={"body": f"{text}\n\n{marker}"})
        if num in CLOSE and by_number[num]["state"] == "open":
            do(f"close   #{num}", "PATCH", by_number[num]["url"],
               json={"state": "closed", "state_reason": "completed"})


if __name__ == "__main__":
    main()
