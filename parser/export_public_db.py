"""
parser/export_public_db.py — Build a small, trimmed copy of sansad.db for
the public-facing deployment.

The full sansad.db (the real dataset — everything ever scraped) never
leaves this machine. This script copies only the last N days of statements
(plus the members/chunks/pdfs/digests they depend on) into a standalone
public.db with the same schema, FTS rebuilt for that subset only.
push_public_db.py then sends that small file to the live site.

Usage:
    python parser/export_public_db.py --days 30
    python parser/export_public_db.py --days 30 --out public.db
"""

import os
import sys
import argparse
import sqlite3
from pathlib import Path
from datetime import date, timedelta

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _copy(conn, table, where="", params=()):
    cols = ", ".join(_cols(conn, table))
    sql = f"INSERT INTO pub.{table} ({cols}) SELECT {cols} FROM main.{table}"
    if where:
        sql += f" WHERE {where}"
    conn.execute(sql, params)
    return conn.execute(f"SELECT COUNT(*) FROM pub.{table}").fetchone()[0]


def export_public_db(source_path: Path, out_path: Path, days: int):
    if out_path.exists():
        out_path.unlink()

    # Create an empty copy of the current schema at out_path. Must be the
    # first import of core.db in this process so it picks up the env var.
    os.environ["SANSAD_DB_PATH"] = str(out_path)
    from core.db import init_db
    init_db()

    conn = sqlite3.connect(str(source_path))
    conn.execute("ATTACH DATABASE ? AS pub", (str(out_path),))

    # "Last N days" is relative to the newest sitting date actually in the
    # data, not wall-clock today — debate PDFs lag the real calendar.
    latest = conn.execute("SELECT MAX(sitting_date) FROM statements").fetchone()[0]
    if not latest:
        print("No statements in source DB — nothing to export.")
        conn.close()
        return
    latest_date = date.fromisoformat(latest)
    cutoff = (latest_date - timedelta(days=days)).isoformat()

    # sessions / sitting_dates are already seeded by init_db() above (from
    # sessions_data.py, same source as the full DB) — don't copy, would clash.
    n_stmts    = _copy(conn, "statements", "sitting_date >= ?", (cutoff,))
    n_members  = _copy(conn, "members",
        "id IN (SELECT member_id FROM main.statements WHERE sitting_date >= ?)", (cutoff,))
    n_pdfs     = _copy(conn, "source_pdfs",
        "id IN (SELECT source_pdf_id FROM main.statements "
        "WHERE sitting_date >= ? AND source_pdf_id IS NOT NULL)", (cutoff,))
    n_chunks   = _copy(conn, "statement_chunks",
        "statement_id IN (SELECT id FROM main.statements WHERE sitting_date >= ?)", (cutoff,))
    n_digests  = _copy(conn, "digests", "sitting_date >= ?", (cutoff,))
    n_profiles = _copy(conn, "politician_profiles",
        "member_id IN (SELECT member_id FROM main.statements WHERE sitting_date >= ?)", (cutoff,))

    # PIB press releases: same rolling window, but measured from the newest PIB
    # release (independent of the debate lag above). Only fully fetched rows —
    # 'listed'/'error' rows have no body and aren't shown anywhere.
    n_pib = 0
    pib_latest = conn.execute(
        "SELECT MAX(release_date) FROM pib_releases WHERE fetch_status = 'fetched'").fetchone()[0]
    if pib_latest:
        pib_cutoff = (date.fromisoformat(pib_latest) - timedelta(days=days)).isoformat()
        n_pib = _copy(conn, "pib_releases",
                      "fetch_status = 'fetched' AND release_date >= ?", (pib_cutoff,))

    # Party/leader YouTube: registry tables whole (small), fetched videos +
    # their quote chunks for the last N days measured from the newest video.
    n_media = n_mchunks = 0
    for t in ("parties", "people", "affiliations", "source_accounts"):
        _copy(conn, t)
    media_latest = conn.execute(
        "SELECT MAX(published_date) FROM media_items WHERE fetch_status = 'fetched'").fetchone()[0]
    if media_latest:
        media_cutoff = (date.fromisoformat(media_latest) - timedelta(days=days)).isoformat()
        n_media = _copy(conn, "media_items",
                        "fetch_status = 'fetched' AND published_date >= ?", (media_cutoff,))
        n_mchunks = _copy(conn, "media_chunks",
            "item_id IN (SELECT id FROM main.media_items "
            "WHERE fetch_status = 'fetched' AND published_date >= ?)", (media_cutoff,))

    conn.commit()
    conn.execute("DETACH DATABASE pub")
    conn.close()

    print(f"Exported public.db (last {days} days, cutoff {cutoff}) -> {out_path}")
    print(f"  statements={n_stmts} members={n_members} source_pdfs={n_pdfs} "
          f"chunks={n_chunks} digests={n_digests} profiles={n_profiles} pib_releases={n_pib} "
          f"videos={n_media} video_chunks={n_mchunks}")
    print(f"  size: {out_path.stat().st_size / 1_048_576:.1f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30,
                    help="How many days of statements to include (default: 30)")
    ap.add_argument("--out", default=str(_ROOT / "public.db"))
    ap.add_argument("--source", default=str(_ROOT / "sansad.db"))
    args = ap.parse_args()
    export_public_db(Path(args.source), Path(args.out), args.days)
