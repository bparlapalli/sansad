"""
record/import_reviews.py — load Google Form review answers into rec_reviews.

    python record/import_reviews.py responses.csv
    python record/import_reviews.py responses.csv --dry-run

Input: the response Sheet made by record/review_form.py, downloaded as CSV
(File → Download → Comma-separated values). Columns are mapped by the "(ref: <node_id>)"
suffix in each question title. Re-importing the same CSV is harmless (UNIQUE key).

Reviews never change evidence grades. The importer ends with a to-do list for the
founder: 'yes' answers with a pasted passage (→ add it to the bundle as a verbatim span
and rerun record/verify.py), and 'no' answers / other links (→ triage into a counter-claim).
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db, sync_db  # noqa: E402

REF = re.compile(r"\(ref: ([a-z0-9-]+)\)\s*$")


def verdict(answer: str) -> str | None:
    a = (answer or "").strip()
    if not a:
        return None
    if a.startswith("✅") or a.lower().startswith("yes"):
        return "yes"
    if a.startswith("❌") or a.lower().startswith("no"):
        return "no"
    return "cant_tell"


def parse(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    cols = list(rows[0].keys())
    ts_col = next((c for c in cols if c.lower() in ("timestamp", "zeitstempel")), cols[0])
    name_col = next((c for c in cols if c.strip().lower() == "your name"), None)
    by_node: dict[str, dict[str, str]] = {}
    for c in cols:
        m = REF.search(c)
        if not m:
            continue
        kind = "answer" if "does the source say" in c else "note" if "notes" in c else "link"
        by_node.setdefault(m.group(1), {})[kind] = c

    out = []
    for r in rows:
        reviewer = (r.get(name_col) or "anonymous").strip() if name_col else "anonymous"
        ts = r.get(ts_col, "").strip()
        for node, c in by_node.items():
            v = verdict(r.get(c.get("answer", ""), ""))
            note = (r.get(c.get("note", ""), "") or "").strip() or None
            link = (r.get(c.get("link", ""), "") or "").strip() or None
            if v or note or link:
                out.append(dict(node_id=node, reviewer=reviewer, verdict=v, note=note,
                                counter_url=link, submitted_at=ts))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    reviews = parse(a.csv)
    init_db()
    conn = get_connection()
    known = {r[0] for r in conn.execute("SELECT id FROM rec_nodes")}
    unknown = sorted({r["node_id"] for r in reviews} - known)
    if unknown:
        print("  ! answers for nodes not in the Record (skipped):", ", ".join(unknown))
    added = 0
    for r in reviews:
        if r["node_id"] not in known or a.dry_run:
            continue
        cur = conn.execute("""
            INSERT OR IGNORE INTO rec_reviews (node_id, reviewer, verdict, note, counter_url, submitted_at)
            VALUES (:node_id, :reviewer, :verdict, :note, :counter_url, :submitted_at)""", r)
        added += cur.rowcount
    conn.commit()

    print(f"✓ {len(reviews)} answers read, {added} new stored"
          f"{' (dry run — nothing stored)' if a.dry_run else ''}  [{datetime.now():%Y-%m-%d %H:%M}]")
    todo = conn.execute("""
        SELECT node_id, reviewer, verdict, note, counter_url FROM rec_reviews
        WHERE status = 'new' AND (note IS NOT NULL OR counter_url IS NOT NULL OR verdict = 'no')
        ORDER BY node_id""").fetchall()
    conn.close()
    sync_db()
    if todo:
        print("\nFounder to-do (status='new'):")
        for t in todo:
            action = ("paste passage into bundle as verbatim span → rerun verify.py" if t["verdict"] == "yes"
                      else "triage: counter-claim node + 'contradicts' edge, or dismiss")
            print(f"  • {t['node_id']} — {t['reviewer']}: {t['verdict'] or '—'}"
                  f"{' | note: ' + t['note'][:120] if t['note'] else ''}"
                  f"{' | link: ' + t['counter_url'] if t['counter_url'] else ''}\n      → {action}")


if __name__ == "__main__":
    main()
