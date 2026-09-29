"""
record/claims_page.py — one readable page of every claim in a story: its grade, the exact passage
the verifier located, and (when present) what that passage does NOT establish.

    SANSAD_DB_PATH=data/research/hyderabad/record.db \
        python record/claims_page.py hyd-post-1 data/research/hyderabad --out claims.md

The Record tables are the single source of truth (docs/HYDERABAD_WEDGE.md §8); this is another
generated view of them, next to the wiki stubs. Gaps come from <bundle>/verbatim_spans.json.
Private output — contains unverified draft claims; never write it into the public repo.
"""
import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection  # noqa: E402

SECTIONS = [("boomed", "Why some areas boomed"), ("risk", "What could stall growth"),
            ("next", "Where growth may go next"), ("who", "Who said what")]
LEADS_ONLY = {"reference", "listing", "blog"}
GRADE_ORDER = {"confirmed": 0, "reported": 1, "claimed": 2, None: 3}


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def build(story: str, bundle: Path) -> str:
    gaps = {}
    vs = bundle / "verbatim_spans.json"
    if vs.exists():
        gaps = {(v["node"], v["source"]): v.get("gap", "") for v in json.loads(vs.read_text(encoding="utf-8"))}

    conn = get_connection()
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM rec_entities")}
    nodes = conn.execute("""SELECT n.*, sn.section FROM rec_nodes n
                            JOIN rec_story_nodes sn ON sn.node_id = n.id WHERE sn.story_id = ?""",
                         (story,)).fetchall()
    total = len(nodes)
    counts = {}
    for n in nodes:
        counts[n["evidence_grade"] or "unverified"] = counts.get(n["evidence_grade"] or "unverified", 0) + 1

    out = ["# Claims and verification status (PRIVATE)", "",
           f"**{total} claims.** " + " · ".join(f"{k}: {counts[k]}" for k in
                                                 ("confirmed", "reported", "claimed", "unverified") if k in counts), "",
           "How to read this: a grade describes the **located passages listed under each claim**, not the whole wording. "
           "*Gap* says what the passage does **not** establish. Wikipedia, listing sites and blogs are leads only and never count. "
           "A claim marked *(claim)* records that someone **said** something — not that it is true.", ""]

    for key, title in SECTIONS:
        sec = sorted((n for n in nodes if n["section"] == key),
                     key=lambda n: (GRADE_ORDER.get(n["evidence_grade"], 9), n["date"] or "9999"))
        if not sec:
            continue
        out += [f"## {title}", ""]
        for n in sec:
            actor = names.get(n["actor_id"], n["actor_id"] or "")
            claim_tag = " *(claim)*" if n["layer"] == "claim" else ""
            out += [f"### {actor} {n['action']}{claim_tag}", "",
                    f"`{n['id']}` · {n['date'] or 'date unknown'} · **{n['evidence_grade'] or 'unverified'}**", ""]
            srcs = conn.execute("""SELECT ns.source_id, ns.span_text, ns.span_status, s.url, s.publisher, s.source_kind
                                   FROM rec_node_sources ns JOIN rec_sources s ON s.id = ns.source_id
                                   WHERE ns.node_id = ? ORDER BY ns.span_status""", (n["id"],)).fetchall()
            located = [s for s in srcs if s["span_status"] == "located"]
            for s in located:
                lead = " — *lead only, not counted*" if s["source_kind"] in LEADS_ONLY else ""
                out.append(f"- **Located** in [{_cell(s['publisher'])}]({s['url']}) ({s['source_kind']}){lead}")
                out.append(f"  > {_cell(s['span_text'])}")
                gap = gaps.get((n["id"], s["source_id"]))
                if gap:
                    out.append(f"  - *Gap:* {gap}")
            others = [s for s in srcs if s["span_status"] != "located"]
            if others:
                out.append("- Not located: " + ", ".join(
                    f"[{_cell(s['publisher'])}]({s['url']}) ({s['span_status']})" for s in others))
            if not srcs:
                out.append("- No sources attached.")
            out.append("")
    conn.close()
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("bundle", help="bundle dir (for verbatim_spans.json gaps)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    md = build(a.story, Path(a.bundle))
    Path(a.out).write_text(md, encoding="utf-8", newline="\n")
    print(f"wrote {a.out} ({len(md.split())} words)")
