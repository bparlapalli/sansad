"""
app/app.py — ParamaSrota news site

A parliament intelligence news site with:
  - Home: today's digest (Claude) + proceedings
  - Search: FTS5 full-text search with filters
  - Topic: deep dive with timeline across all sittings
  - Speaker: profile page with all their statements
  - Sessions: overview of all sessions
  - Stats: database statistics

Run:
    python app/app.py
    Open: http://localhost:5100
"""

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import unquote

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from flask import Flask, render_template, request, jsonify, redirect, url_for

from core.db import get_connection, init_db
from app.admin import admin_bp
from app.query import (
    full_text_search, get_stats, get_speakers_list,
    get_latest_dates, get_statements_for_date,
    get_statements_for_topic, get_trending_topics,
    search_by_speaker,
)
from app.digest import get_or_generate_digest, get_latest_sitting_with_data

# ── Flask setup ───────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Run DB migration on startup (adds new columns if DB is from older version) ─
init_db()

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
)

# ── Admin blueprint ───────────────────────────────────────────────────────────
app.register_blueprint(admin_bp)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ticker_text() -> str | None:
    """One-line ticker for the masthead — most recent sitting date."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT sitting_date, COUNT(*) as n
        FROM statements
        GROUP BY sitting_date
        ORDER BY sitting_date DESC
        LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return f"Latest data: {row['sitting_date']}  ·  {row['n']} statements indexed"


def _get_active_speakers_for_date(date_str: str) -> list[dict]:
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT m.name, m.name_normalized, COUNT(*) as cnt
        FROM statements s
        JOIN members m ON s.member_id = m.id
        WHERE s.sitting_date = ?
        GROUP BY m.id
        ORDER BY cnt DESC
        LIMIT 10
    """, (date_str,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _markdown_to_html(text: str) -> str:
    """
    Very basic markdown → HTML for digest display.
    Handles: ## headings, ### subheadings, **bold**, > blockquotes, *italic*, paragraphs.
    """
    import re
    lines    = text.split('\n')
    html     = []
    in_quote = False

    for line in lines:
        # Blockquote
        if line.startswith('>'):
            if not in_quote:
                html.append('<blockquote>')
                in_quote = True
            content = line[1:].strip()
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'_(.+?)_', r'<em>\1</em>', content)
            html.append(f'<p>{content}</p>')
            continue
        if in_quote:
            html.append('</blockquote>')
            in_quote = False

        # Headings
        if line.startswith('## '):
            text_content = line[3:].strip()
            html.append(f'<h2>{text_content}</h2>')
        elif line.startswith('### '):
            text_content = line[4:].strip()
            html.append(f'<h3>{text_content}</h3>')
        elif line.startswith('#### '):
            text_content = line[5:].strip()
            html.append(f'<h4>{text_content}</h4>')
        elif line.strip() == '':
            html.append('')
        else:
            content = line
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\*(.+?)\*',     r'<em>\1</em>', content)
            content = re.sub(r'_(.+?)_',       r'<em>\1</em>', content)
            html.append(f'<p>{content}</p>')

    if in_quote:
        html.append('</blockquote>')

    return '\n'.join(html)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    # Which date to show
    selected_date = request.args.get("date")
    all_dates     = get_latest_dates(limit=20)
    has_data      = bool(all_dates)

    if not has_data:
        return render_template(
            "home.html",
            active_tab="home",
            has_data=False,
            ticker_text=None,
        )

    if not selected_date:
        selected_date = all_dates[0]["sitting_date"] if all_dates else None

    if not selected_date:
        return render_template("home.html", active_tab="home", has_data=False, ticker_text=None)

    # Format date for display
    try:
        display_date = datetime.strptime(selected_date, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    except ValueError:
        display_date = selected_date

    # Load statements for this date
    statements       = get_statements_for_date(selected_date, limit=80)
    active_speakers  = _get_active_speakers_for_date(selected_date)
    stats            = get_stats()
    ticker           = _get_ticker_text()

    # Try to get/generate digest
    no_api_key = not os.getenv("ANTHROPIC_API_KEY")
    digest     = None
    if not no_api_key:
        raw_digest = get_or_generate_digest(selected_date)
        if raw_digest:
            # Convert markdown to HTML for template
            digest = dict(raw_digest)
            digest["digest_text"] = _markdown_to_html(raw_digest["digest_text"])

    return render_template(
        "home.html",
        active_tab      = "home",
        has_data        = True,
        selected_date   = selected_date,
        display_date    = display_date,
        all_dates       = all_dates,
        statements      = statements,
        active_speakers = active_speakers,
        digest          = digest,
        no_api_key      = no_api_key,
        stats           = stats,
        ticker_text     = ticker,
    )


@app.route("/search")
def search():
    q       = request.args.get("q", "").strip()
    speaker = request.args.get("speaker", "").strip()
    session = request.args.get("session", "").strip()
    stype   = request.args.get("type", "").strip()
    searched = bool(q or speaker or session or stype)

    results = []
    total   = 0

    if searched:
        results, total = full_text_search(
            query_text=q,
            speaker=speaker or None,
            session=int(session) if session else None,
            stype=stype or None,
            limit=50,
        )

    # Sidebar data
    trending     = get_trending_topics(limit=12) if not searched else []
    recent_dates = get_latest_dates(limit=8)      if not searched else []
    top_speakers = get_speakers_list()[:10]        if not searched else []

    return render_template(
        "search.html",
        active_tab   = "search",
        q            = q,
        speaker      = speaker,
        session      = session,
        stype        = stype,
        searched     = searched,
        results      = results,
        total        = total,
        trending     = trending,
        recent_dates = recent_dates,
        top_speakers = top_speakers,
        ticker_text  = _get_ticker_text(),
    )


@app.route("/topic/<path:topic>")
def topic(topic: str):
    topic = unquote(topic)

    statements = get_statements_for_topic(topic, limit=60)

    # Get unique dates and speakers for sidebar
    dates   = sorted(set(s["sitting_date"] for s in statements))
    speaker_counts: dict[str, dict] = {}
    for s in statements:
        n = s.get("name_normalized") or s["speaker_raw"].lower()
        if n not in speaker_counts:
            speaker_counts[n] = {
                "name":             s["speaker_raw"].title(),
                "name_normalized":  n,
                "cnt":              0,
            }
        speaker_counts[n]["cnt"] += 1

    speakers_on_topic = sorted(speaker_counts.values(), key=lambda x: -x["cnt"])[:10]

    # Add name_normalized to statements for template links
    for s in statements:
        if "name_normalized" not in s:
            s["name_normalized"] = s["speaker_raw"].lower()

    return render_template(
        "topic.html",
        active_tab        = "search",
        topic             = topic,
        statements        = statements,
        dates             = dates,
        speakers_on_topic = speakers_on_topic,
        related_topics    = [],
        ticker_text       = _get_ticker_text(),
    )


@app.route("/speaker/<path:name_normalized>")
def speaker(name_normalized: str):
    name_normalized = unquote(name_normalized)

    conn = get_connection()
    c    = conn.cursor()
    c.execute("SELECT * FROM members WHERE name_normalized = ?", (name_normalized,))
    member = c.fetchone()
    conn.close()

    if not member:
        return redirect(url_for("search"))

    member = dict(member)
    rows   = search_by_speaker(member["name"], limit=40)

    dates_active = len(set(r["sitting_date"] for r in rows))
    total        = len(rows)

    # Type breakdown
    type_counts: dict[str, int] = {}
    for r in rows:
        t = r["statement_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    type_breakdown = [{"statement_type": t, "cnt": n}
                      for t, n in sorted(type_counts.items(), key=lambda x: -x[1])]

    return render_template(
        "speaker.html",
        active_tab     = "speakers",
        member         = member,
        statements     = rows,
        total          = total,
        dates_active   = dates_active,
        type_breakdown = type_breakdown,
        ticker_text    = _get_ticker_text(),
    )


@app.route("/speakers")
def speakers_list():
    speakers = get_speakers_list()

    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT m.name, m.name_normalized, m.constituency, m.party,
               COUNT(s.id) as cnt
        FROM members m
        LEFT JOIN statements s ON s.member_id = m.id
        GROUP BY m.id
        HAVING cnt > 0
        ORDER BY cnt DESC
    """)
    all_speakers = [dict(r) for r in c.fetchall()]
    conn.close()

    # Inline HTML for speakers list (simple page)
    from flask import render_template_string
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>All Speakers — ParamaSrota</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: sans-serif; background: #f8f7f2; color: #1a1a1a; }
.top { background: #0f2818; color: #fff; padding: 14px 32px; }
.top h1 { font-size: 1.2rem; font-weight: 700; }
.top a { color: rgba(255,255,255,0.6); font-size:0.82rem; }
.content { max-width: 900px; margin: 0 auto; padding: 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.card { background: #fff; border: 1px solid #e4e0d8; border-radius: 4px; padding: 14px 16px; }
.card a { color: #0f2818; font-weight: 700; font-size: 0.9rem; }
.meta { font-size: 0.77rem; color: #888; margin-top: 2px; }
.count { font-size: 0.75rem; color: #2a6a3a; margin-top: 4px; font-weight: 600; }
</style>
</head>
<body>
<div class="top">
  <p><a href="/">← Home</a></p>
  <h1 style="margin-top:6px;">All Speakers ({{ speakers | length }})</h1>
</div>
<div class="content">
  <input type="text" id="filter" placeholder="Filter speakers…"
    oninput="filterList(this.value)"
    style="width:100%;max-width:400px;height:38px;padding:0 12px;border:1px solid #d4d0c8;border-radius:4px;font-size:0.9rem;margin-bottom:20px;outline:none;">
  <div class="grid" id="grid">
    {% for sp in speakers %}
    <div class="card sp-card" data-name="{{ sp.name | lower }}">
      <div><a href="/speaker/{{ sp.name_normalized }}">{{ sp.name | title }}</a></div>
      {% if sp.constituency %}<div class="meta">{{ sp.constituency }}</div>{% endif %}
      {% if sp.party %}<div class="meta">{{ sp.party }}</div>{% endif %}
      <div class="count">{{ sp.cnt }} statement{{ 's' if sp.cnt != 1 }}</div>
    </div>
    {% endfor %}
  </div>
</div>
<script>
function filterList(q) {
  q = q.toLowerCase();
  document.querySelectorAll('.sp-card').forEach(el => {
    el.style.display = el.dataset.name.includes(q) ? '' : 'none';
  });
}
</script>
</body>
</html>
""", speakers=all_speakers)


@app.route("/sessions")
def sessions_page():
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT s.*, COUNT(sd.id) as total_dates, SUM(sd.has_debate_pdf) as downloaded_pdfs
        FROM sessions s
        LEFT JOIN sitting_dates sd ON sd.session_id = s.id
        GROUP BY s.id
        ORDER BY s.lok_sabha_no, s.session_no
    """)
    all_sessions = [dict(r) for r in c.fetchall()]
    conn.close()

    from flask import render_template_string
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sessions — ParamaSrota</title>
<style>
*, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
body { font-family:sans-serif; background:#f8f7f2; color:#1a1a1a; }
.top { background:#0f2818;color:#fff;padding:14px 32px; }
.top h1 { font-size:1.2rem;font-weight:700; }
.top a { color:rgba(255,255,255,0.6);font-size:0.82rem; }
.content { max-width:900px;margin:0 auto;padding:24px; }
table { width:100%;border-collapse:collapse;background:#fff;border:1px solid #e4e0d8;border-radius:4px;overflow:hidden; }
th { background:#f0ede6;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px;padding:10px 14px;text-align:left; }
td { padding:10px 14px;border-top:1px solid #f0ede6;font-size:0.85rem; }
tr:hover td { background:#fafaf8; }
.badge { display:inline-block;font-size:0.7rem;font-weight:700;padding:2px 7px;border-radius:3px;text-transform:uppercase; }
.badge-budget  { background:#fff0e0;color:#8b4000; }
.badge-winter  { background:#e0e8ff;color:#1a2a6e; }
.badge-monsoon { background:#e0f5e8;color:#1a5e30; }
.badge-special { background:#f5e0ff;color:#4a1a6e; }
</style>
</head>
<body>
<div class="top">
  <p><a href="/">← Home</a></p>
  <h1 style="margin-top:6px;">Sessions — 18th Lok Sabha</h1>
</div>
<div class="content">
  <table>
    <thead>
      <tr>
        <th>#</th><th>Session</th><th>Type</th><th>Dates</th>
        <th>Sittings</th><th>PDFs</th><th>Notes</th>
      </tr>
    </thead>
    <tbody>
      {% for s in sessions %}
      <tr>
        <td>{{ s.session_no }}</td>
        <td><a href="/?date={{ s.start_date }}" style="color:#0f2818;font-weight:600;">{{ s.session_name }}</a></td>
        <td><span class="badge badge-{{ s.session_type }}">{{ s.session_type }}</span></td>
        <td style="white-space:nowrap;font-size:0.8rem;color:#666;">{{ s.start_date }}{% if s.end_date %} – {{ s.end_date }}{% endif %}</td>
        <td style="text-align:center;">{{ s.total_dates }}</td>
        <td style="text-align:center;">{{ s.downloaded_pdfs or 0 }}</td>
        <td style="font-size:0.78rem;color:#888;max-width:300px;">{{ (s.notes or '')[:120] }}{% if s.notes and s.notes|length > 120 %}…{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
</body>
</html>
""", sessions=all_sessions)


@app.route("/stats")
def stats():
    data = get_stats()
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stats — ParamaSrota</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:sans-serif;background:#f8f7f2;color:#1a1a1a;}
.top{background:#0f2818;color:#fff;padding:14px 32px;}
.top h1{font-size:1.2rem;font-weight:700;}
.top a{color:rgba(255,255,255,0.6);font-size:0.82rem;}
.content{max-width:800px;margin:0 auto;padding:24px;}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:32px;}
.stat-box{background:#fff;border:1px solid #e4e0d8;border-radius:4px;padding:20px;text-align:center;}
.n{font-size:2rem;font-weight:700;color:#0f2818;}
.l{font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;color:#888;margin-top:4px;}
h2{font-size:1rem;font-weight:700;margin:24px 0 12px;text-transform:uppercase;letter-spacing:0.5px;color:#555;}
.list-card{background:#fff;border:1px solid #e4e0d8;border-radius:4px;overflow:hidden;}
.list-row{display:flex;justify-content:space-between;padding:10px 16px;border-top:1px solid #f0ede6;font-size:0.85rem;}
.list-row:first-child{border-top:none;}
</style>
</head>
<body>
<div class="top">
  <p><a href="/">← Home</a></p>
  <h1 style="margin-top:6px;">Database Stats</h1>
</div>
<div class="content">
  <div class="grid">
    <div class="stat-box"><div class="n">{{ data.total_stmts }}</div><div class="l">Statements</div></div>
    <div class="stat-box"><div class="n">{{ data.unique_speakers }}</div><div class="l">Speakers</div></div>
    <div class="stat-box"><div class="n">{{ data.pdfs_parsed }}</div><div class="l">PDFs Parsed</div></div>
  </div>

  <h2>Top Speakers</h2>
  <div class="list-card">
    {% for s in data.top_speakers %}
    <div class="list-row">
      <a href="/speaker/{{ s.name | lower | replace(' ', '_') }}" style="color:#0f2818;">{{ s.name | title }}</a>
      <span style="color:#888;">{{ s.cnt }}</span>
    </div>
    {% endfor %}
  </div>

  <h2>Statements by Date</h2>
  <div class="list-card">
    {% for d in data.by_date %}
    <div class="list-row">
      <a href="/?date={{ d.sitting_date }}" style="color:#0f2818;">{{ d.sitting_date }}</a>
      <span style="color:#888;">{{ d.cnt }}</span>
    </div>
    {% endfor %}
  </div>
</div>
</body>
</html>
""", data=data)


# ── API endpoints (for AJAX) ──────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    q       = request.args.get("q", "").strip()
    speaker = request.args.get("speaker", "").strip()
    session = request.args.get("session", "").strip()
    stype   = request.args.get("type", "").strip()
    limit   = int(request.args.get("limit", 50))

    results, total = full_text_search(
        query_text=q,
        speaker=speaker or None,
        session=int(session) if session else None,
        stype=stype or None,
        limit=limit,
    )
    return jsonify({"total": total, "results": results})


@app.route("/api/speakers")
def api_speakers():
    return jsonify(get_speakers_list())


@app.route("/api/digest/<date_str>")
def api_digest(date_str: str):
    from app.digest import generate_digest_for_date
    force  = request.args.get("force", "0") == "1"
    result = generate_digest_for_date(date_str, force=force)
    if result:
        return jsonify(result)
    return jsonify({"error": "Could not generate digest"}), 404


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🏛  ParamaSrota — Parliament Intelligence")
    print("   Open: http://localhost:5100\n")
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("   ⚠  ANTHROPIC_API_KEY not set — AI digest disabled")
    if not os.getenv("SARVAM_API_KEY"):
        print("   ⚠  SARVAM_API_KEY not set — Hindi translation disabled")
    print()
    app.run(port=5100, debug=False)
