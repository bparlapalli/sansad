"""
parser/backfill_chunks.py — Chunk every existing statement that has no
chunks yet (or all statements, with --force).

Usage:
    python parser/backfill_chunks.py            # only statements missing chunks
    python parser/backfill_chunks.py --force     # re-chunk everything
"""

import sys
import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db, sync_db
from parser.chunker import store_chunks


def backfill(force: bool = False):
    init_db()   # ensures statement_chunks / chunks_fts exist before we query them
    conn = get_connection()
    c = conn.cursor()

    if force:
        c.execute("SELECT id, statement_text FROM statements")
    else:
        c.execute("""
            SELECT s.id, s.statement_text
            FROM statements s
            LEFT JOIN statement_chunks ch ON ch.statement_id = s.id
            WHERE ch.id IS NULL
        """)
    rows = c.fetchall()

    if not rows:
        print("Nothing to backfill — every statement already has chunks.")
        conn.close()
        return

    print(f"Chunking {len(rows)} statement(s)...")
    total_chunks = 0
    for i, row in enumerate(rows, start=1):
        if force:
            c.execute("DELETE FROM statement_chunks WHERE statement_id = ?", (row["id"],))
        total_chunks += store_chunks(conn, row["id"], row["statement_text"])
        if i % 200 == 0:
            conn.commit()
            print(f"  ...{i}/{len(rows)}")

    conn.commit()
    sync_db()
    conn.close()
    print(f"Done — {len(rows)} statement(s) → {total_chunks} chunk(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-chunk every statement, not just ones missing chunks")
    args = parser.parse_args()
    backfill(force=args.force)
