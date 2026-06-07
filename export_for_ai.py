"""
export_for_ai.py — Export statements + top MPs to JSON for AI generation

Run from the sansad/ project root:
    python export_for_ai.py

Then attach export_for_ai.json to your Cowork/Claude session.
"""
import sqlite3
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for candidate in ["sansad.db", "sansad.db.bak"]:
    p = _HERE / candidate
    if p.exists() and p.stat().st_size > 10000:
        DB_PATH = p
        break
else:
    print("Database not found.")
    raise SystemExit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
c = conn.cursor()

# ── All statements (for digest generation) ────────────────────────────────────
c.execute("""
    SELECT s.sitting_date, s.speaker_raw, s.statement_type,
           s.statement_text, s.word_count, s.topic,
           m.party, m.constituency
    FROM statements s
    JOIN members m ON s.member_id = m.id
    WHERE s.word_count >= 30
    ORDER BY s.sitting_date, s.page_number
""")
statements = [dict(r) for r in c.fetchall()]
print(f"Exported {len(statements):,} statements across "
      f"{len(set(r['sitting_date'] for r in statements))} dates")

# ── Top 20 MPs with their statements (for profile generation) ─────────────────
c.execute("""
    SELECT m.id, m.name, m.party, m.constituency,
           COUNT(s.id) as stmt_count
    FROM members m
    JOIN statements s ON s.member_id = m.id
    GROUP BY m.id
    ORDER BY stmt_count DESC
    LIMIT 20
""")
top_mps = [dict(r) for r in c.fetchall()]

for mp in top_mps:
    c.execute("""
        SELECT statement_type, statement_text, sitting_date, topic
        FROM statements
        WHERE member_id = ?
        ORDER BY sitting_date, page_number
        LIMIT 100
    """, (mp["id"],))
    mp["statements"] = [dict(r) for r in c.fetchall()]

print(f"Exported top {len(top_mps)} MPs")

# ── Already-generated content (skip these) ────────────────────────────────────
existing_tables = {r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
done_dates    = set()
done_profiles = set()
if "digests" in existing_tables:
    done_dates = {r[0] for r in c.execute("SELECT sitting_date FROM digests")}
if "politician_profiles" in existing_tables:
    done_profiles = {r[0] for r in c.execute("SELECT member_id FROM politician_profiles")}

conn.close()

out = {
    "statements":    statements,
    "top_mps":       top_mps,
    "done_dates":    sorted(done_dates),
    "done_profiles": sorted(done_profiles),
}

out_path = _HERE / "export_for_ai.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

size_mb = out_path.stat().st_size / 1_000_000
print(f"Written: export_for_ai.json  ({size_mb:.1f} MB)")
print("Attach this file to your Cowork/Claude session to generate digests + profiles.")
