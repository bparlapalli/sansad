"""
Scraper status dashboard — standalone FastAPI app.
Shows what PDFs are downloaded, when, parse stats, and coverage gaps.

Run:  uvicorn status:app --reload --port 8001
Or add to main FastAPI app:  app.include_router(router, prefix="/status")
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ParamaSrota — Scraper Status")

DB_PATH = os.getenv("DB_PATH", "sansad.db")
STATUS_JSON = Path("scraper_status.json")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_status_data() -> dict:
    conn = get_db()

    # PDFs table
    pdfs = conn.execute("""
        SELECT
            sp.filename,
            sp.session_id,
            sp.sitting_date,
            sp.pages,
            sp.downloaded_at,
            COUNT(st.id) AS statement_count
        FROM source_pdfs sp
        LEFT JOIN statements st ON st.pdf_id = sp.id
        GROUP BY sp.id
        ORDER BY sp.sitting_date DESC
    """).fetchall()

    # Summary counts
    total_pdfs   = conn.execute("SELECT COUNT(*) FROM source_pdfs").fetchone()[0]
    total_stmts  = conn.execute("SELECT COUNT(*) FROM statements").fetchone()[0]
    total_members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]

    # Sessions coverage
    sessions = conn.execute("""
        SELECT s.id, s.name, s.session_type,
               COUNT(DISTINCT sd.date) AS expected_sittings,
               COUNT(DISTINCT sp.sitting_date) AS downloaded_sittings
        FROM sessions s
        LEFT JOIN sitting_dates sd ON sd.session_id = s.id
        LEFT JOIN source_pdfs sp ON sp.session_id = s.id
        GROUP BY s.id
        ORDER BY s.id
    """).fetchall()

    # Last run info from JSON if available
    last_run = None
    if STATUS_JSON.exists():
        with open(STATUS_JSON) as f:
            last_run = json.load(f)

    conn.close()
    return {
        "pdfs": [dict(r) for r in pdfs],
        "sessions": [dict(r) for r in sessions],
        "total_pdfs": total_pdfs,
        "total_statements": total_stmts,
        "total_members": total_members,
        "last_run": last_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/", response_class=HTMLResponse)
async def status_dashboard():
    d = get_status_data()

    last_run_html = ""
    if d["last_run"]:
        lr = d["last_run"]
        last_run_html = f"""
        <div class="card">
          <h2>Last Cron Run</h2>
          <table>
            <tr><th>Run at</th><td>{lr.get('run_at','—')}</td></tr>
            <tr><th>Total PDFs</th><td>{lr.get('total_pdfs','—')}</td></tr>
            <tr><th>Total Statements</th><td>{lr.get('total_statements','—')}</td></tr>
            <tr><th>Latest PDF</th><td>{lr.get('latest_pdf','—')}</td></tr>
          </table>
        </div>"""

    sessions_rows = ""
    for s in d["sessions"]:
        pct = (s["downloaded_sittings"] / s["expected_sittings"] * 100) if s["expected_sittings"] else 0
        gap = s["expected_sittings"] - s["downloaded_sittings"]
        color = "#2ecc71" if pct == 100 else ("#f39c12" if pct > 0 else "#e74c3c")
        sessions_rows += f"""
        <tr>
          <td>{s['id']}</td>
          <td>{s['name']}</td>
          <td>{s['session_type']}</td>
          <td>{s['expected_sittings']}</td>
          <td style="color:{color};font-weight:bold">{s['downloaded_sittings']}</td>
          <td style="color:{'#e74c3c' if gap > 0 else '#2ecc71'}">{gap} missing</td>
          <td>
            <div style="background:#333;border-radius:4px;height:10px;width:100px;display:inline-block">
              <div style="background:{color};border-radius:4px;height:10px;width:{min(pct,100):.0f}px"></div>
            </div>
            {pct:.0f}%
          </td>
        </tr>"""

    pdf_rows = ""
    for p in d["pdfs"]:
        pdf_rows += f"""
        <tr>
          <td>{p['sitting_date'] or '—'}</td>
          <td><code>{p['filename']}</code></td>
          <td>{p['session_id']}</td>
          <td>{p['pages'] or '—'}</td>
          <td>{"✅ " + str(p['statement_count']) if p['statement_count'] else "⚠️ 0"}</td>
          <td style="font-size:0.8em;color:#999">{(p['downloaded_at'] or '')[:19]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ParamaSrota — Scraper Status</title>
  <meta http-equiv="refresh" content="300"> <!-- auto-refresh every 5 min -->
  <style>
    body {{ font-family: system-ui, sans-serif; background: #111; color: #eee; margin: 0; padding: 20px; }}
    h1   {{ color: #f90; margin-bottom: 4px; }}
    h2   {{ color: #aaa; font-size: 0.95em; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 8px; }}
    .subtitle {{ color: #666; font-size: 0.85em; margin-bottom: 24px; }}
    .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
    .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px; min-width: 180px; }}
    .card .num {{ font-size: 2em; font-weight: bold; color: #f90; }}
    table {{ width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 8px; overflow: hidden; margin-bottom: 24px; }}
    th {{ background: #222; color: #999; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 12px; text-align: left; }}
    td {{ padding: 9px 12px; border-top: 1px solid #2a2a2a; font-size: 0.9em; }}
    tr:hover td {{ background: #1f1f1f; }}
    code {{ background: #2a2a2a; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; }}
    .section-title {{ color: #f90; font-size: 1.1em; font-weight: bold; margin: 24px 0 8px; }}
  </style>
</head>
<body>
  <h1>ParamaSrota — Scraper Status</h1>
  <div class="subtitle">Generated {d['generated_at'][:19]} UTC · Auto-refreshes every 5 min</div>

  <div class="cards">
    <div class="card"><h2>PDFs Downloaded</h2><div class="num">{d['total_pdfs']}</div></div>
    <div class="card"><h2>Statements Parsed</h2><div class="num">{d['total_statements']:,}</div></div>
    <div class="card"><h2>Members Known</h2><div class="num">{d['total_members']}</div></div>
  </div>

  {last_run_html}

  <div class="section-title">Session Coverage</div>
  <table>
    <thead><tr>
      <th>#</th><th>Session</th><th>Type</th>
      <th>Expected Sittings</th><th>Downloaded</th><th>Gap</th><th>Coverage</th>
    </tr></thead>
    <tbody>{sessions_rows}</tbody>
  </table>

  <div class="section-title">Downloaded PDFs</div>
  <table>
    <thead><tr>
      <th>Date</th><th>File</th><th>Session</th><th>Pages</th><th>Statements</th><th>Downloaded At</th>
    </tr></thead>
    <tbody>{pdf_rows or '<tr><td colspan="6" style="color:#666;text-align:center">No PDFs yet</td></tr>'}</tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/api/status")
async def status_json():
    """Machine-readable status — useful for alerting / monitoring."""
    return get_status_data()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
