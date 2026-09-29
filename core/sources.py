"""
core/sources.py — Registry of data sources, so the app can treat them uniformly.

Each source (Parliament debates, PIB press releases, later YouTube, ...) plugs in
two functions and nothing else in the app needs to change:

    recent(conn, limit, **filters) -> [Item]   # newest first — feeds the running list
    search(conn, query, limit)     -> [Item]   # full-text match — feeds topic pages

An Item is a plain dict with the same keys for every source:

    source, source_label, id, title, date (YYYY-MM-DD), sort_key (for ordering
    within/between days), subtitle (speaker / ministry), snippet (HTML-safe,
    may contain <mark>), url (internal page)

To add a source: write its two functions, call register(...) at the bottom.
The /feed page and /t/<topic> pages pick it up automatically.
"""

import html
import re
from dataclasses import dataclass
from typing import Callable

_HL_OPEN, _HL_CLOSE = "\x02", "\x03"   # private markers so snippet() output can be escaped safely


@dataclass
class Source:
    key: str
    label: str
    recent: Callable
    search: Callable
    home_url: str          # the source's own browse page
    colour: str            # badge colour in the UI


SOURCES: dict[str, Source] = {}


def register(source: Source):
    SOURCES[source.key] = source


# ── Helpers ───────────────────────────────────────────────────────────────────

def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query: every word quoted, implicit AND.
    (Splitting on whitespace rather than \\w keeps Devanagari matras intact.)"""
    terms = [t for t in text.replace('"', " ").split() if t]
    return " ".join(f'"{t}"' for t in terms)


def _highlight(marked: str) -> str:
    """Escape a snippet() result and turn the private markers into <mark> tags."""
    return (html.escape(marked)
            .replace(_HL_OPEN, "<mark>").replace(_HL_CLOSE, "</mark>"))


def _plain_snippet(text: str, n: int = 260) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return html.escape(text[:n] + ("…" if len(text) > n else ""))


# ── Parliament debates ────────────────────────────────────────────────────────

def _parl_item(r, snippet_html):
    who = (r["speaker_raw"] or "").title()
    return {
        "source": "parliament", "source_label": "Parliament",
        "id": r["id"],
        "title": f"{who} — {r['topic'] or r['statement_type']}",
        "date": r["sitting_date"], "sort_key": r["sitting_date"],
        "subtitle": " · ".join(x for x in (r["party"], r["constituency"]) if x),
        "snippet": snippet_html,
        "url": f"/?date={r['sitting_date']}",
    }


_PARL_COLS = """s.id, s.speaker_raw, s.sitting_date, s.statement_type, s.topic,
                m.party, m.constituency"""


def _parl_recent(conn, limit=30, **_):
    rows = conn.execute(f"""
        SELECT {_PARL_COLS}, s.statement_text AS text
        FROM statements s LEFT JOIN members m ON s.member_id = m.id
        ORDER BY s.sitting_date DESC, s.id DESC LIMIT ?""", (limit,)).fetchall()
    return [_parl_item(r, _plain_snippet(r["text"])) for r in rows]


def _parl_search(conn, query, limit=20):
    q = fts_query(query)
    if not q:
        return []
    rows = conn.execute(f"""
        SELECT {_PARL_COLS},
               snippet(chunks_fts, 0, '{_HL_OPEN}', '{_HL_CLOSE}', '…', 40) AS snip
        FROM chunks_fts
        JOIN statement_chunks ch ON chunks_fts.rowid = ch.id
        JOIN statements s        ON ch.statement_id  = s.id
        LEFT JOIN members m      ON s.member_id      = m.id
        WHERE chunks_fts MATCH ?
        ORDER BY s.sitting_date DESC, s.id DESC LIMIT ?""", (q, limit)).fetchall()
    return [_parl_item(r, _highlight(r["snip"])) for r in rows]


# ── PIB press releases ────────────────────────────────────────────────────────

def _pib_item(r, snippet_html):
    return {
        "source": "pib", "source_label": "PIB",
        "id": r["prid"],
        "title": r["title"],
        "date": r["release_date"], "sort_key": r["posted_at"] or r["release_date"],
        "subtitle": r["ministry"] or "",
        "snippet": snippet_html,
        "url": f"/pib/{r['prid']}",
    }


def _pib_recent(conn, limit=30, ministry=None, **_):
    sql = """SELECT prid, title, ministry, release_date, posted_at, body_text
             FROM pib_releases WHERE fetch_status = 'fetched'"""
    params = []
    if ministry:
        sql += " AND ministry = ?"
        params.append(ministry)
    sql += " ORDER BY COALESCE(posted_at, release_date) DESC LIMIT ?"
    params.append(limit)
    return [_pib_item(r, _plain_snippet(r["body_text"]))
            for r in conn.execute(sql, params).fetchall()]


def _pib_search(conn, query, limit=20):
    q = fts_query(query)
    if not q:
        return []
    rows = conn.execute(f"""
        SELECT p.prid, p.title, p.ministry, p.release_date, p.posted_at,
               snippet(pib_releases_fts, 2, '{_HL_OPEN}', '{_HL_CLOSE}', '…', 40) AS snip
        FROM pib_releases_fts
        JOIN pib_releases p ON pib_releases_fts.rowid = p.id
        WHERE pib_releases_fts MATCH ? AND p.fetch_status = 'fetched'
        ORDER BY COALESCE(p.posted_at, p.release_date) DESC LIMIT ?""", (q, limit)).fetchall()
    return [_pib_item(r, _highlight(r["snip"])) for r in rows]


register(Source("parliament", "Parliament", _parl_recent, _parl_search, "/search",  "#1a4a2e"))
register(Source("pib",        "PIB",        _pib_recent,  _pib_search,  "/pib",     "#8a4b08"))


# ── Cross-source views ────────────────────────────────────────────────────────

def _selected(keys):
    return [SOURCES[k] for k in (keys or SOURCES) if k in SOURCES]


def running_list(conn, limit=50, keys=None) -> list[dict]:
    """Newest items across the chosen sources, merged into one list."""
    items = []
    for src in _selected(keys):
        items += src.recent(conn, limit=limit)
    items.sort(key=lambda i: i["sort_key"] or "", reverse=True)
    return items[:limit]


def topic_view(conn, topic, per_source=20) -> dict:
    """Everything every source has on `topic`: per-source hits plus one merged timeline."""
    by_source = {}
    for src in SOURCES.values():
        by_source[src.key] = src.search(conn, topic, limit=per_source)
    timeline = sorted((i for hits in by_source.values() for i in hits),
                      key=lambda i: i["sort_key"] or "", reverse=True)
    return {"by_source": by_source, "timeline": timeline}
