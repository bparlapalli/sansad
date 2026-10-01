"""
scrapers/indicators/store.py — shared upsert helpers for indicator pipelines.

Tables live in core/record_schema.py (rec_series, rec_geo, rec_observations).
Every helper is idempotent: re-running with identical input changes nothing.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_db():
    """Open the local sansad.db with the Record tables guaranteed to exist."""
    from core.db import get_connection
    from core.record_schema import create_record_tables
    conn = get_connection()
    create_record_tables(conn)
    return conn


def ensure_series(conn, sid, name, unit, measure, geo_level, cadence,
                  source_family, licence, description):
    conn.execute(
        """INSERT INTO rec_series(id,name,unit,measure,geo_level,cadence,source_family,licence,description)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, unit=excluded.unit, measure=excluded.measure,
             geo_level=excluded.geo_level, cadence=excluded.cadence, source_family=excluded.source_family,
             licence=excluded.licence, description=excluded.description""",
        (sid, name, unit, measure, geo_level, cadence, source_family, licence, description))


def ensure_geo(conn, gid, level, name, parent_id=None, source=None, lat=None, lon=None):
    """Insert a geography once; never overwrites an existing row. Returns True if new."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO rec_geo(id,level,name,parent_id,lat,lon,source) VALUES(?,?,?,?,?,?,?)",
        (gid, level, name, parent_id, lat, lon, source))
    return cur.rowcount > 0


def upsert_observation(conn, series_id, entity_id, period, value, source_url,
                       source_file_sha, note=None) -> str:
    """Returns 'new', 'changed' or 'same'. 'same' writes nothing (retrieved_at untouched)."""
    row = conn.execute(
        "SELECT value, source_file_sha, note FROM rec_observations WHERE series_id=? AND entity_id=? AND period=?",
        (series_id, entity_id, period)).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO rec_observations(series_id,entity_id,period,value,source_url,source_file_sha,retrieved_at,note)
               VALUES(?,?,?,?,?,?,?,?)""",
            (series_id, entity_id, period, value, source_url, source_file_sha, now_iso(), note))
        return "new"
    if row[0] == value and row[1] == source_file_sha and row[2] == note:
        return "same"
    conn.execute(
        """UPDATE rec_observations SET value=?, source_url=?, source_file_sha=?, retrieved_at=?, note=?
           WHERE series_id=? AND entity_id=? AND period=?""",
        (value, source_url, source_file_sha, now_iso(), note, series_id, entity_id, period))
    return "changed"
