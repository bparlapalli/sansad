"""
record/wiki.py — generate Record (wiki) stub pages from the Record tables.

    python record/wiki.py data/hyderabad/wiki               # every entity cited by any story
    python record/wiki.py data/hyderabad/wiki --story hyd-post-1
    python record/wiki.py data/hyderabad/wiki --all         # every entity, cited or not

Pages are generated, never hand-written (HYDERABAD_WEDGE.md §8: the post, the timeline
and the wiki are three views of the same tables). Output is markdown into a private
directory; publish_state stays 'private' until the founder approves. Nothing here
publishes anything.
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection  # noqa: E402

GRADE = lambda g: g or "unverified"  # noqa: E731


def cited_entities(conn, story: str | None) -> list[str]:
    """Every entity a story node touches: its actor, its claimant, or a linked place/subject."""
    rows = conn.execute("""
        SELECT n.actor_id, n.claimant_id, ne.entity_id
        FROM rec_story_nodes sn
        JOIN rec_nodes n ON n.id = sn.node_id
        LEFT JOIN rec_node_entities ne ON ne.node_id = n.id
        WHERE ? IS NULL OR sn.story_id = ?""", (story, story)).fetchall()
    return sorted({x for r in rows for x in r if x})


def page(conn, eid: str) -> str:
    e = dict(conn.execute("SELECT * FROM rec_entities WHERE id=?", (eid,)).fetchone())
    src = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM rec_sources")}
    out = [f"# {e['name']}", "",
           f"*{e['type']} · `{eid}` · **{e['publish_state']}** — generated stub, do not hand-edit*", ""]
    aliases = json.loads(e["aliases"] or "[]")
    if aliases:
        out += [f"**Also known as:** {', '.join(aliases)}", ""]
    if e["summary"]:
        out += [e["summary"], ""]

    attrs = conn.execute("""SELECT * FROM rec_entity_attrs WHERE entity_id=?
                            ORDER BY attr, COALESCE(valid_from,'')""", (eid,)).fetchall()
    if attrs:
        out += ["## Attributes (dated history — never overwritten)", "",
                "| Attribute | Value | From | To | Grade | Source |", "|---|---|---|---|---|---|"]
        for a in attrs:
            s = src.get(a["source_id"]) or {}
            link = f"[{s.get('publisher', a['source_id'])}]({s['url']})" if s else "—"
            out.append(f"| {a['attr']} | {a['value']} | {a['valid_from'] or '…'} | {a['valid_to'] or 'current?'} "
                       f"| {GRADE(a['evidence_grade'])} ({a['span_status']}) | {link} |")
        out.append("")

    nodes = conn.execute("""
        SELECT DISTINCT n.* FROM rec_nodes n
        LEFT JOIN rec_node_entities ne ON ne.node_id = n.id
        WHERE n.actor_id = ? OR n.claimant_id = ? OR ne.entity_id = ?
        ORDER BY COALESCE(n.date, '9999')""", (eid, eid, eid)).fetchall()
    if nodes:
        out += ["## Timeline", "",
                "| Date | What happened | Role | Weight | Grade | Sources |", "|---|---|---|---|---|---|"]
        for n in nodes:
            ss = conn.execute("SELECT source_id, span_status FROM rec_node_sources WHERE node_id=?", (n["id"],)).fetchall()
            links = ", ".join(f"[{src[s['source_id']]['publisher']}]({src[s['source_id']]['url']})" for s in ss)
            actor = "" if n["actor_id"] == eid else f"**{n['actor_id']}** "
            layer = " *(claim)*" if n["layer"] == "claim" else ""
            out.append(f"| {n['date'] or 'date?'} ({n['date_precision']}) | {actor}{n['action']}{layer} "
                       f"| {n['role'] or '—'} ({n['role_status']}) | {n['weight'] or '—'} ({n['weight_status']}) "
                       f"| {GRADE(n['evidence_grade'])} | {links} |")
        out.append("")

    stories = conn.execute("""
        SELECT DISTINCT s.id, s.title FROM rec_stories s JOIN rec_story_nodes sn ON sn.story_id = s.id
        LEFT JOIN rec_nodes n ON n.id = sn.node_id LEFT JOIN rec_node_entities ne ON ne.node_id = n.id
        WHERE n.actor_id = ? OR n.claimant_id = ? OR ne.entity_id = ?""", (eid, eid, eid)).fetchall()
    out += [f"## Cited in {len(stories)} stor{'y' if len(stories) == 1 else 'ies'}", ""]
    out += [f"- {s['title']} (`{s['id']}`)" for s in stories] + [""]

    gate = any(a["evidence_grade"] for a in attrs) or any(n["evidence_grade"] for n in nodes)
    out += ["---", f"*Publish gate (STORY_ENGINE §4): cited by a published story AND ≥1 graded source — "
                   f"{'grade present' if gate else 'NOT MET: no graded attribute or node yet'}.*", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--story")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    conn = get_connection()
    ids = [r[0] for r in conn.execute("SELECT id FROM rec_entities ORDER BY id")] if a.all \
        else cited_entities(conn, a.story)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    index = ["# Record — generated stubs (PRIVATE)", "", "| Page | Type | Gate |", "|---|---|---|"]
    for eid in ids:
        md = page(conn, eid)
        (a.out_dir / f"{eid}.md").write_text(md, encoding="utf-8")
        typ = conn.execute("SELECT type FROM rec_entities WHERE id=?", (eid,)).fetchone()[0]
        index.append(f"| [{eid}]({eid}.md) | {typ} | {'grade present' if 'grade present' in md else 'not met'} |")
    (a.out_dir / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    conn.close()
    print(f"✓ {len(ids)} stub pages → {a.out_dir}")


if __name__ == "__main__":
    main()
