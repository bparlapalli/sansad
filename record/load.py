"""
record/load.py — load a research bundle (JSON) into the Record tables.

    python record/load.py data/hyderabad          # loads sources/entities/nodes/edges.json
    python record/load.py data/hyderabad --dry-run

The bundle lives under data/ (gitignored): research drafts, roles and weights are
not public until the founder publishes. Bundle files:

  sources.json   [{id, url, title, publisher, independence_key, source_kind,
                   published_date, discovered_via, access, access_notes, terms_notes}]
  entities.json  [{id, type, name, aliases[], summary,
                   attrs: [{attr, value, valid_from, valid_to, precision, source, span}]}]
  nodes.json     [{id, story, section, date, precision, actor, action, decision_text,
                   role, weight, intent, counterfactual, comparison, layer, claimant,
                   entities: [[entity_id, relation]], sources: [{source, span, verbatim}]}]
  edges.json     [{from, to, relation, note}]
  stories.json   [{id, title}]

Rules enforced here:
  - Attributes are append-only. Loading a bundle never UPDATEs an attribute row;
    a changed value must arrive as a new row with its own valid_from.
  - Evidence grades are NEVER loaded from JSON — only record/verify.py sets them.
  - Roles / weights always load as 'proposed'; founder confirmation happens in the DB.
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db, sync_db  # noqa: E402

ROLES   = {"deliberate_bet", "spillover", "unblocker", "roadblock", "wildcard"}
WEIGHTS = {"essential", "accelerant", "minor"}
KINDS   = {"primary", "court", "official_statement", "news", "research",
           "listing", "party_statement", "reference", "dataset"}


def _read(bundle: Path, name: str) -> list:
    p = bundle / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def validate(bundle: Path) -> list[str]:
    """Return a list of problems; empty = OK."""
    errs = []
    sources  = {s["id"]: s for s in _read(bundle, "sources.json")}
    entities = {e["id"]: e for e in _read(bundle, "entities.json")}
    nodes    = _read(bundle, "nodes.json")
    node_ids = {n["id"] for n in nodes}

    for s in sources.values():
        if s.get("source_kind") not in KINDS:
            errs.append(f"source {s['id']}: bad source_kind {s.get('source_kind')!r}")
    for e in entities.values():
        for a in e.get("attrs", []):
            if a.get("source") and a["source"] not in sources:
                errs.append(f"entity {e['id']}.{a['attr']}: unknown source {a['source']}")
    for n in nodes:
        if not n.get("sources"):
            errs.append(f"node {n['id']}: no source (rule: no node without a source span)")
        for s in n.get("sources", []):
            if s["source"] not in sources:
                errs.append(f"node {n['id']}: unknown source {s['source']}")
            if not s.get("span"):
                errs.append(f"node {n['id']}: source {s['source']} has no span text")
        if n.get("role") and n["role"] not in ROLES:
            errs.append(f"node {n['id']}: bad role {n['role']!r}")
        if n.get("weight") and n["weight"] not in WEIGHTS:
            errs.append(f"node {n['id']}: bad weight {n['weight']!r}")
        for ref in [n.get("actor"), n.get("claimant")] + [x[0] for x in n.get("entities", [])]:
            if ref and ref not in entities:
                errs.append(f"node {n['id']}: entity {ref!r} has no entity row (every node must resolve to a page)")
    for e in _read(bundle, "edges.json"):
        for k in ("from", "to"):
            if e[k] not in node_ids:
                errs.append(f"edge {e['from']}->{e['to']}: unknown node {e[k]}")
    return errs


def load(bundle: Path) -> dict:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    counts = dict(sources=0, entities=0, attrs=0, nodes=0, edges=0)

    for s in _read(bundle, "sources.json"):
        c.execute("""
            INSERT INTO rec_sources (id, url, title, publisher, independence_key, source_kind,
                                     published_date, discovered_via, access, access_notes, terms_notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                url=excluded.url, title=excluded.title, publisher=excluded.publisher,
                independence_key=excluded.independence_key, source_kind=excluded.source_kind,
                published_date=excluded.published_date, access=excluded.access,
                access_notes=excluded.access_notes, terms_notes=excluded.terms_notes
        """, (s["id"], s["url"], s.get("title"), s.get("publisher"),
              s.get("independence_key") or s.get("publisher"), s["source_kind"],
              s.get("published_date"), s.get("discovered_via"), s.get("access", "unchecked"),
              s.get("access_notes"), s.get("terms_notes")))
        counts["sources"] += 1

    for e in _read(bundle, "entities.json"):
        c.execute("""
            INSERT INTO rec_entities (id, type, name, aliases, summary)
            VALUES (?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET type=excluded.type, name=excluded.name,
                aliases=excluded.aliases, summary=excluded.summary
        """, (e["id"], e["type"], e["name"], json.dumps(e.get("aliases", []), ensure_ascii=False),
              e.get("summary")))
        counts["entities"] += 1
        for a in e.get("attrs", []):
            # append-only: INSERT OR IGNORE, never UPDATE
            c.execute("""
                INSERT OR IGNORE INTO rec_entity_attrs
                    (entity_id, attr, value, valid_from, valid_to, date_precision, source_id, span_text)
                VALUES (?,?,?,?,?,?,?,?)
            """, (e["id"], a["attr"], str(a["value"]), a.get("valid_from"), a.get("valid_to"),
                  a.get("precision", "day"), a.get("source"), a.get("span")))
            counts["attrs"] += c.rowcount

    for s in _read(bundle, "stories.json"):
        c.execute("INSERT OR IGNORE INTO rec_stories (id, title) VALUES (?,?)", (s["id"], s["title"]))

    for n in _read(bundle, "nodes.json"):
        c.execute("""
            INSERT INTO rec_nodes (id, date, date_precision, actor_id, action, decision_text,
                                   role, weight, intent_toward_outcome, counterfactual_note,
                                   comparison_case, layer, claimant_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                date=excluded.date, date_precision=excluded.date_precision,
                actor_id=excluded.actor_id, action=excluded.action,
                decision_text=excluded.decision_text,
                -- a founder-confirmed role/weight is never overwritten by a bundle reload
                role   = CASE WHEN rec_nodes.role_status   = 'confirmed' THEN rec_nodes.role   ELSE excluded.role   END,
                weight = CASE WHEN rec_nodes.weight_status = 'confirmed' THEN rec_nodes.weight ELSE excluded.weight END,
                intent_toward_outcome=excluded.intent_toward_outcome,
                counterfactual_note=excluded.counterfactual_note,
                comparison_case=excluded.comparison_case, layer=excluded.layer,
                claimant_id=excluded.claimant_id
        """, (n["id"], n.get("date"), n.get("precision", "day"), n.get("actor"), n["action"],
              n.get("decision_text"), n.get("role"), n.get("weight"),
              None if n.get("intent") is None else int(bool(n["intent"])),
              n.get("counterfactual"), n.get("comparison"), n.get("layer", "fact"),
              n.get("claimant")))
        counts["nodes"] += 1
        if n.get("story"):
            c.execute("INSERT OR REPLACE INTO rec_story_nodes (story_id, node_id, section) VALUES (?,?,?)",
                      (n["story"], n["id"], n.get("section")))
        for ent, rel in n.get("entities", []):
            c.execute("INSERT OR IGNORE INTO rec_node_entities (node_id, entity_id, relation) VALUES (?,?,?)",
                      (n["id"], ent, rel))
        for s in n.get("sources", []):
            c.execute("""
                INSERT INTO rec_node_sources (node_id, source_id, span_text, span_is_verbatim)
                VALUES (?,?,?,?)
                ON CONFLICT(node_id, source_id) DO UPDATE SET
                    span_text=excluded.span_text, span_is_verbatim=excluded.span_is_verbatim
            """, (n["id"], s["source"], s["span"], int(bool(s.get("verbatim")))))

    for e in _read(bundle, "edges.json"):
        c.execute("""INSERT OR IGNORE INTO rec_edges (from_node, to_node, relation, note)
                     VALUES (?,?,?,?)""", (e["from"], e["to"], e["relation"], e.get("note")))
        counts["edges"] += c.rowcount

    conn.commit()
    conn.close()
    sync_db()
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="validate only")
    args = ap.parse_args()

    errs = validate(args.bundle)
    for e in errs:
        print("  ✗", e)
    if errs:
        sys.exit(f"{len(errs)} problem(s) — fix the bundle before loading")
    print("✓ bundle valid")
    if not args.dry_run:
        print("✓ loaded:", load(args.bundle))


if __name__ == "__main__":
    main()
