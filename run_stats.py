"""
run_stats.py — ParamaSrota database stats
Run from the sansad/ project root:
    python run_stats.py
"""
import sqlite3
import sys
from pathlib import Path

# Try both main DB and backup
_HERE = Path(__file__).resolve().parent
for candidate in ["sansad.db", "sansad.db.bak"]:
    p = _HERE / candidate
    if p.exists() and p.stat().st_size > 10000:
        DB_PATH = p
        break
else:
    print("Database not found. Run 'python main.py --status' first.")
    sys.exit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Discover which tables actually exist
existing_tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}

BAR = "=" * 65

# ── Overview ──────────────────────────────────────────────────────────────────
c.execute("SELECT COUNT(*) FROM members")
total_members = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM members WHERE party IS NOT NULL")
with_party = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM statements")
total_stmts = c.fetchone()[0]

c.execute("SELECT COUNT(DISTINCT sitting_date) FROM statements")
total_dates = c.fetchone()[0]

total_digests  = 0
total_profiles = 0
if "digests" in existing_tables:
    c.execute("SELECT COUNT(*) FROM digests")
    total_digests = c.fetchone()[0]
if "politician_profiles" in existing_tables:
    c.execute("SELECT COUNT(*) FROM politician_profiles")
    total_profiles = c.fetchone()[0]

print(f"\n{BAR}")
print("  ParamaSrota -- Database Stats  ({})".format(DB_PATH.name))
print(BAR)
print(f"  Politicians  : {total_members}  ({with_party} with party data)")
print(f"  Statements   : {total_stmts:,}")
print(f"  Sitting dates: {total_dates}")
print(f"  AI digests   : {total_digests} / {total_dates} dates")
print(f"  AI profiles  : {total_profiles} / {total_members} politicians")
print(BAR)

# ── Top 20 politicians by statement count ─────────────────────────────────────
print(f"\n  TOP 20 POLITICIANS BY STATEMENTS")

profile_join = ""
profile_col  = "'n/a' as has_profile"
if "politician_profiles" in existing_tables:
    profile_join = "LEFT JOIN politician_profiles p ON p.member_id = m.id"
    profile_col  = "CASE WHEN p.id IS NOT NULL THEN 'yes' ELSE '-' END as has_profile"

print(f"  {'Name':<40} {'Party':<14} {'Stmts':>5}  {'Days':>4}  {'Profile'}")
print(f"  {'-'*40} {'-'*14} {'-'*5}  {'-'*4}  {'-'*7}")
c.execute(f"""
    SELECT m.name, COALESCE(m.party, '?') as party,
           COUNT(s.id) as cnt,
           COUNT(DISTINCT s.sitting_date) as days,
           {profile_col}
    FROM members m
    JOIN statements s ON s.member_id = m.id
    {profile_join}
    GROUP BY m.id
    ORDER BY cnt DESC
    LIMIT 20
""")
for r in c.fetchall():
    name = r["name"][:38] + ".." if len(r["name"]) > 38 else r["name"]
    print(f"  {name:<40} {r['party']:<14} {r['cnt']:>5}  {r['days']:>4}  {r['has_profile']}")

# ── Statements by party ───────────────────────────────────────────────────────
print(f"\n  STATEMENTS BY PARTY")
print(f"  {'Party':<22} {'MPs':>4}  {'Statements':>10}  {'Dates':>5}")
print(f"  {'-'*22} {'-'*4}  {'-'*10}  {'-'*5}")
c.execute("""
    SELECT COALESCE(m.party, 'Unknown') as party,
           COUNT(DISTINCT m.id) as members,
           COUNT(s.id) as stmts,
           COUNT(DISTINCT s.sitting_date) as dates
    FROM members m
    LEFT JOIN statements s ON s.member_id = m.id
    GROUP BY party
    ORDER BY stmts DESC
""")
for r in c.fetchall():
    print(f"  {r['party']:<22} {r['members']:>4}  {r['stmts']:>10,}  {r['dates']:>5}")

# ── Sitting dates ─────────────────────────────────────────────────────────────
print(f"\n  SITTING DATES")
print(f"  {'Date':<12} {'Statements':>10}  {'Speakers':>8}  {'Digest':>7}")
print(f"  {'-'*12} {'-'*10}  {'-'*8}  {'-'*7}")
digest_join = ""
digest_col  = "'n/a' as has_digest"
if "digests" in existing_tables:
    digest_join = "LEFT JOIN digests d ON d.sitting_date = s.sitting_date"
    digest_col  = "CASE WHEN d.id IS NOT NULL THEN 'yes' ELSE '-' END as has_digest"
c.execute(f"""
    SELECT s.sitting_date,
           COUNT(s.id) as stmts,
           COUNT(DISTINCT s.member_id) as speakers,
           {digest_col}
    FROM statements s
    {digest_join}
    GROUP BY s.sitting_date
    ORDER BY s.sitting_date DESC
""")
for r in c.fetchall():
    print(f"  {r['sitting_date']:<12} {r['stmts']:>10,}  {r['speakers']:>8}  {r['has_digest']:>7}")

# ── Source PDFs ───────────────────────────────────────────────────────────────
if "source_pdfs" in existing_tables:
    c.execute("SELECT parse_status, COUNT(*) as n FROM source_pdfs GROUP BY parse_status")
    pdf_counts = {r["parse_status"]: r["n"] for r in c.fetchall()}
    print(f"\n  SOURCE PDFs: ", end="")
    for status, n in sorted(pdf_counts.items()):
        print(f"{status}={n}  ", end="")
    print()

print(f"\n{BAR}\n")
conn.close()
