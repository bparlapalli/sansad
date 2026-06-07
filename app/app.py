"""
app/app.py -- ParamaSrota Flask application

Blueprints:
  admin_bp   -> /admin  (scraper control, catalog, parser)
  search_bp  -> /search (unified search: date/politician/party/text)

Run:
    python app/app.py   ->  http://localhost:5100
"""
import sys, os, re, logging
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from flask import Flask, render_template, request, jsonify, redirect, url_for
from core.db import get_connection, init_db
from app.admin import admin_bp
from app.search_bp import search_bp
from app.query import (
    get_stats, get_speakers_list, get_latest_dates,
    get_statements_for_date, get_statements_for_topic,
    search_by_speaker, get_news_briefing, get_parsed_pdfs,
)
from app.digest import get_or_generate_digest, get_cached_profile

logging.basicConfig(level=logging.INFO)

init_db()

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.register_blueprint(admin_bp)
app.register_blueprint(search_bp)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ticker():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT sitting_date, COUNT(*) as n FROM statements "
              "GROUP BY sitting_date ORDER BY sitting_date DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return f"Latest: {row['sitting_date']}  ·  {row['n']} statements" if row else None


def _active_speakers(date_str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT m.name, m.name_normalized, COUNT(*) as cnt
                 FROM statements s JOIN members m ON s.member_id = m.id
                 WHERE s.sitting_date = ?
                 GROUP BY m.id ORDER BY cnt DESC LIMIT 10""", (date_str,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _md_to_html(text):
    lines, html, in_q = text.split("\n"), [], False
    for line in lines:
        if line.startswith(">"):
            if not in_q: html.append("<blockquote>"); in_q = True
            html.append(f"<p>{line[1:].strip()}</p>"); continue
        if in_q: html.append("</blockquote>"); in_q = False
        if line.startswith("## "): html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "): html.append(f"<h3>{line[4:]}</h3>")
        elif line.strip() == "": html.append("")
        else:
            c2 = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            html.append(f"<p>{c2}</p>")
    if in_q: html.append("</blockquote>")
    return "\n".join(html)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    all_dates = get_latest_dates(limit=20)
    if not all_dates:
        return render_template("home.html", active_tab="home", has_data=False, ticker_text=None)
    selected = request.args.get("date") or all_dates[0]["sitting_date"]
    try:    display = datetime.strptime(selected, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    except: display = selected
    no_key = not os.getenv("ANTHROPIC_API_KEY")
    digest = None
    if not no_key:
        raw = get_or_generate_digest(selected)
        if raw:
            digest = dict(raw)
            digest["digest_text"] = _md_to_html(raw["digest_text"])
    return render_template("home.html",
        active_tab=("home"), has_data=True,
        selected_date=selected, display_date=display,
        all_dates=all_dates, statements=get_statements_for_date(selected, 80),
        active_speakers=_active_speakers(selected), digest=digest,
        no_api_key=no_key, stats=get_stats(), ticker_text=_ticker())


@app.route("/pdfs")
def pdfs_page():
    return render_template("pdfs.html", active_tab="pdfs",
                           pdfs=get_parsed_pdfs(), ticker_text=_ticker())


@app.route("/news")
def news():
    return render_template("news.html", active_tab="news",
                           briefing=get_news_briefing(12), ticker_text=_ticker())


@app.route("/topic/<path:topic>")
def topic_page(topic):
    topic = unquote(topic)
    stmts = get_statements_for_topic(topic, 60)
    dates = sorted({s["sitting_date"] for s in stmts})
    sc = {}
    for s in stmts:
        n = s.get("name_normalized") or s["speaker_raw"].lower()
        sc.setdefault(n, {"name": s["speaker_raw"].title(), "name_normalized": n, "cnt": 0})
        sc[n]["cnt"] += 1
    for s in stmts:
        s.setdefault("name_normalized", s["speaker_raw"].lower())
    return render_template("topic.html", active_tab="search", topic=topic,
        statements=stmts, dates=dates,
        speakers_on_topic=sorted(sc.values(), key=lambda x: -x["cnt"])[:10],
        related_topics=[], ticker_text=_ticker())


@app.route("/speaker/<path:slug>")
def speaker_page(slug):
    slug = unquote(slug)
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM members WHERE name_normalized = ?", (slug,))
    member = c.fetchone(); conn.close()
    if not member: return redirect(url_for("search_bp.search"))
    member = dict(member)
    rows = search_by_speaker(member["name_normalized"], limit=40)
    tc = {}
    for r in rows: tc[r["statement_type"]] = tc.get(r["statement_type"], 0) + 1
    profile = get_cached_profile(member["id"])
    return render_template("speaker.html", active_tab="speakers", member=member,
        statements=rows, total=len(rows),
        dates_active=len({r["sitting_date"] for r in rows}),
        type_breakdown=[{"statement_type": t, "cnt": n}
                        for t, n in sorted(tc.items(), key=lambda x: -x[1])],
        profile=profile,
        ticker_text=_ticker())


@app.route("/speakers")
def speakers_list():
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT m.name, m.name_normalized, m.constituency, m.party, COUNT(s.id) as cnt
                 FROM members m LEFT JOIN statements s ON s.member_id=m.id
                 GROUP BY m.id HAVING cnt>0 ORDER BY cnt DESC""")
    speakers = [dict(r) for r in c.fetchall()]; conn.close()
    return render_template("speakers_list.html", speakers=speakers, ticker_text=_ticker())


@app.route("/sessions")
def sessions_page():
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT s.*, COUNT(sd.id) as total_dates, SUM(sd.has_debate_pdf) as downloaded_pdfs
                 FROM sessions s LEFT JOIN sitting_dates sd ON sd.session_id=s.id
                 GROUP BY s.id ORDER BY s.lok_sabha_no, s.session_no""")
    sessions = [dict(r) for r in c.fetchall()]; conn.close()
    return render_template("sessions.html", sessions=sessions, ticker_text=_ticker())


@app.route("/stats")
def stats():
    return render_template("stats.html", data=get_stats(), ticker_text=_ticker())


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    from app.query import full_text_search
    q, spk = request.args.get("q","").strip(), request.args.get("speaker","").strip()
    sess   = request.args.get("session","").strip()
    limit  = int(request.args.get("limit", 50))
    results, total = full_text_search(q, spk or None, int(sess) if sess else None, limit=limit)
    return jsonify({"total": total, "results": results})


@app.route("/api/speakers")
def api_speakers():
    return jsonify(get_speakers_list())


@app.route("/api/digest/<date_str>")
def api_digest(date_str):
    from app.digest import generate_digest_for_date
    result = generate_digest_for_date(date_str, force=request.args.get("force","0")=="1")
    return jsonify(result) if result else (jsonify({"error": "not found"}), 404)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nParamaSrota -- http://localhost:5100\n")
    app.run(port=5100, debug=False)
