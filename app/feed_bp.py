"""
app/feed_bp.py — Multi-source views, built on core/sources.py.

  /feed            running list across every source (filter with ?source=pib)
  /pib             PIB press releases — filter by ministry / date / text
  /pib/<prid>      one press release
  /t               topic hub landing
  /t/<topic>       everything every source has on one topic

Adding a source to core/sources.py makes it show up in /feed and /t/<topic>
automatically; only a source-specific browse page (like /pib) needs its own route.
"""
import json

from flask import Blueprint, abort, render_template, request

from core.db import get_connection
from core.sources import SOURCES, fts_query, running_list, topic_view

feed_bp = Blueprint("feed_bp", __name__)


def _ticker():
    conn = get_connection()
    row = conn.execute("SELECT MAX(release_date) d, COUNT(*) n FROM pib_releases "
                       "WHERE fetch_status = 'fetched'").fetchone()
    conn.close()
    return f"PIB latest: {row['d']}  ·  {row['n']} releases" if row and row["d"] else None


@feed_bp.route("/feed")
def feed():
    source = request.args.get("source", "")
    limit = min(request.args.get("limit", 50, type=int), 300)
    conn = get_connection()
    items = running_list(conn, limit=limit, keys=[source] if source in SOURCES else None)
    conn.close()
    return render_template("feed.html", active_tab="feed", ticker_text=_ticker(),
                           items=items, sources=SOURCES, source=source, limit=limit)


@feed_bp.route("/pib")
def pib_list():
    ministry = request.args.get("ministry", "").strip()
    day = request.args.get("date", "").strip()
    q = request.args.get("q", "").strip()
    limit = min(request.args.get("limit", 50, type=int), 300)

    conn = get_connection()
    ministries = conn.execute("""SELECT ministry, COUNT(*) n FROM pib_releases
                                 WHERE fetch_status = 'fetched' AND ministry IS NOT NULL
                                 GROUP BY ministry ORDER BY n DESC""").fetchall()
    days = conn.execute("""SELECT release_date d, COUNT(*) n FROM pib_releases
                           WHERE fetch_status = 'fetched'
                           GROUP BY d ORDER BY d DESC LIMIT 60""").fetchall()

    if q:
        sql = """SELECT p.prid, p.title, p.ministry, p.release_date, p.posted_at,
                        p.word_count,
                        snippet(pib_releases_fts, 2, '\x02', '\x03', '…', 40) AS snip
                 FROM pib_releases_fts JOIN pib_releases p ON pib_releases_fts.rowid = p.id
                 WHERE pib_releases_fts MATCH ? AND p.fetch_status = 'fetched'"""
        params = [fts_query(q)]
    else:
        sql = """SELECT prid, title, ministry, release_date, posted_at, word_count,
                        substr(body_text, 1, 260) AS snip
                 FROM pib_releases p WHERE fetch_status = 'fetched'"""
        params = []
    if ministry:
        sql += " AND p.ministry = ?"
        params.append(ministry)
    if day:
        sql += " AND p.release_date = ?"
        params.append(day)
    sql += " ORDER BY COALESCE(p.posted_at, p.release_date) DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    import html
    releases = []
    for r in rows:
        d = dict(r)
        d["snip"] = (html.escape(d["snip"] or "")
                     .replace("\x02", "<mark>").replace("\x03", "</mark>"))
        releases.append(d)

    return render_template("pib_list.html", active_tab="pib", ticker_text=_ticker(),
                           releases=releases, ministries=ministries, days=days,
                           ministry=ministry, day=day, q=q, limit=limit)


@feed_bp.route("/pib/<int:prid>")
def pib_release(prid):
    conn = get_connection()
    row = conn.execute("SELECT * FROM pib_releases WHERE prid = ? AND fetch_status = 'fetched'",
                       (prid,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    rel = dict(row)
    rel["translations"] = json.loads(rel["translations"]) if rel["translations"] else {}
    rel["paragraphs"] = [p for p in (rel["body_text"] or "").split("\n") if p.strip()]
    return render_template("pib_release.html", active_tab="pib", ticker_text=_ticker(), rel=rel)


@feed_bp.route("/t")
def topic_index():
    return render_template("topic_hub.html", active_tab="topics", ticker_text=_ticker(),
                           topic=None, view=None, sources=SOURCES)


@feed_bp.route("/t/<path:topic>")
def topic_hub(topic):
    topic = topic.strip()
    if not fts_query(topic):
        abort(404)
    conn = get_connection()
    view = topic_view(conn, topic)
    conn.close()
    return render_template("topic_hub.html", active_tab="topics", ticker_text=_ticker(),
                           topic=topic, view=view, sources=SOURCES)
