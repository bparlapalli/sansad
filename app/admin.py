"""
app/admin.py — ParamaSrota Admin UI
Flask Blueprint mounted at /admin

Features:
  - Overview dashboard: catalog stats, parse status, recent downloads
  - Catalog browser: filterable/paginated table of all discovered PDFs
  - Scraper control: trigger catalog/resolve/download phases with live log
  - Parser control: trigger parse + optional Sarvam translation with live log

All routes return HTML except /api/* which return JSON or SSE streams.
This is localhost-only — no auth needed.

Usage:
    Registered in app.py:
        from app.admin import admin_bp
        app.register_blueprint(admin_bp)
    Then visit: http://localhost:5100/admin
"""

import os
import sys
import json
import time
import uuid
import threading
import subprocess
from pathlib import Path
from datetime import datetime

from flask import (
    Blueprint, render_template_string, request, jsonify,
    Response, redirect, url_for, stream_with_context,
)

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ── Background job registry ───────────────────────────────────────────────────
# Each job: {id, cmd, status, log, returncode, started_at}
# status: 'running' | 'done' | 'error'
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Keep only the last N completed jobs
_MAX_COMPLETED_JOBS = 20


def _start_job(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    """Spawn a subprocess job and return its job_id."""
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id":         job_id,
        "cmd":        " ".join(cmd),
        "status":     "running",
        "log":        [],
        "returncode": None,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job
        # Prune old completed jobs if we have too many
        done = [jid for jid, j in _jobs.items() if j["status"] != "running"]
        for old_id in done[:-_MAX_COMPLETED_JOBS]:
            del _jobs[old_id]

    def _run():
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(cwd),
                bufsize=1,
                env=merged_env,
            )
            job["process"] = proc
            for line in proc.stdout:
                job["log"].append(line.rstrip())
            proc.wait()
            job["returncode"] = proc.returncode
            job["status"] = "done" if proc.returncode == 0 else "error"
        except Exception as exc:
            job["log"].append(f"[FATAL] {exc}")
            job["status"] = "error"
        finally:
            job["finished_at"] = datetime.now().isoformat()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return job_id


# ── DB helpers ────────────────────────────────────────────────────────────────

def _catalog_stats() -> dict:
    """Return quick aggregate stats from the catalog table."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM catalog")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM catalog WHERE downloaded = 1")
    downloaded = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM catalog WHERE downloaded = 0 AND filename IS NOT NULL")
    ready = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM catalog WHERE filename IS NULL")
    unresolved = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM source_pdfs")
    registered = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM statements")
    statements = c.fetchone()[0]

    c.execute("""
        SELECT collection_name, COUNT(*) as n, SUM(downloaded) as dl
        FROM catalog
        GROUP BY collection_name
        ORDER BY n DESC
        LIMIT 10
    """)
    by_collection = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT debate_type, COUNT(*) as n
        FROM catalog
        WHERE debate_type IS NOT NULL
        GROUP BY debate_type
        ORDER BY n DESC
        LIMIT 15
    """)
    by_debate_type = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT doc_id, title, item_date, collection_name, filename, language,
               downloaded_at, file_size_kb
        FROM catalog
        WHERE downloaded = 1
        ORDER BY downloaded_at DESC
        LIMIT 15
    """)
    recent_downloads = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "total":           total,
        "downloaded":      downloaded,
        "ready_to_dl":     ready,
        "unresolved":      unresolved,
        "registered":      registered,
        "statements":      statements,
        "by_collection":   by_collection,
        "by_debate_type":  by_debate_type,
        "recent_downloads": recent_downloads,
    }


def _get_catalog_page(page: int, per_page: int, filters: dict) -> tuple[list, int]:
    """Return paginated catalog rows and total count matching filters."""
    conn = get_connection()
    c = conn.cursor()

    where_clauses = []
    params: list = []

    if filters.get("collection"):
        where_clauses.append("collection_name = ?")
        params.append(filters["collection"])
    if filters.get("language"):
        where_clauses.append("language = ?")
        params.append(filters["language"])
    if filters.get("status") == "downloaded":
        where_clauses.append("downloaded = 1")
    elif filters.get("status") == "pending":
        where_clauses.append("downloaded = 0 AND filename IS NOT NULL")
    elif filters.get("status") == "unresolved":
        where_clauses.append("filename IS NULL")
    if filters.get("from_date"):
        where_clauses.append("item_date >= ?")
        params.append(filters["from_date"])
    if filters.get("to_date"):
        where_clauses.append("item_date <= ?")
        params.append(filters["to_date"])
    if filters.get("debate_type"):
        where_clauses.append("debate_type = ?")
        params.append(filters["debate_type"])
    if filters.get("search"):
        where_clauses.append("(title LIKE ? OR debate_type LIKE ?)")
        term = f"%{filters['search']}%"
        params.extend([term, term])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    c.execute(f"SELECT COUNT(*) FROM catalog {where_sql}", params)
    total = c.fetchone()[0]

    offset = (page - 1) * per_page
    c.execute(f"""
        SELECT doc_id, item_date, title, collection_name, language,
               debate_type, lok_sabha_no, session_no_raw, filename,
               file_size_kb, downloaded, downloaded_at, local_path
        FROM catalog
        {where_sql}
        ORDER BY item_date DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows, total


def _get_distinct_filter_values() -> dict:
    """Get unique values for filter dropdowns."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT collection_name FROM catalog ORDER BY collection_name")
    collections = [r[0] for r in c.fetchall()]
    c.execute("SELECT DISTINCT language FROM catalog WHERE language IS NOT NULL ORDER BY language")
    languages = [r[0] for r in c.fetchall()]
    c.execute("SELECT DISTINCT debate_type FROM catalog WHERE debate_type IS NOT NULL ORDER BY debate_type")
    debate_types = [r[0] for r in c.fetchall()]
    conn.close()
    return {"collections": collections, "languages": languages, "debate_types": debate_types}


def _get_pending_parse() -> list[dict]:
    """PDFs registered in source_pdfs but not yet parsed (no statements)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT sp.id, sp.filename, sp.sitting_date, sp.session_no,
               sp.filename_type, sp.language,
               COUNT(st.id) as stmt_count,
               sp.downloaded_at
        FROM source_pdfs sp
        LEFT JOIN statements st ON st.source_pdf_id = sp.id
        GROUP BY sp.id
        ORDER BY sp.sitting_date DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── Admin base HTML template ──────────────────────────────────────────────────

_ADMIN_BASE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}Admin{% endblock %} — ParamaSrota Admin</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', 'Segoe UI', sans-serif; background: #f0f2f5; color: #1a1a1a; font-size: 14px; }
a { color: #1a4a2e; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Admin header ── */
.adm-header {
  background: #0f2818;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  height: 52px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.adm-logo { font-weight: 700; font-size: 1rem; letter-spacing: -0.3px; }
.adm-logo span { opacity: 0.45; font-weight: 400; margin-left: 8px; font-size: 0.8rem; }
.adm-back { color: rgba(255,255,255,0.55); font-size: 0.8rem; transition: color 0.15s; }
.adm-back:hover { color: #fff; text-decoration: none; }

/* ── Tab nav ── */
.adm-tabs {
  background: #1a3a24;
  padding: 0 28px;
  display: flex;
  gap: 0;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.adm-tabs a {
  color: rgba(255,255,255,0.6);
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.7px;
  padding: 10px 16px;
  display: block;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.adm-tabs a:hover { color: #fff; text-decoration: none; }
.adm-tabs a.active { color: #6ee09a; border-bottom-color: #6ee09a; }

/* ── Page body ── */
.adm-body { max-width: 1400px; margin: 0 auto; padding: 24px 28px; }

/* ── Stat cards ── */
.stat-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
.stat-card {
  background: #fff;
  border: 1px solid #e0e4ea;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-n { font-size: 1.9rem; font-weight: 700; color: #0f2818; line-height: 1; }
.stat-l { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; color: #888; margin-top: 4px; }
.stat-n.green { color: #1a5e30; }
.stat-n.orange { color: #b45200; }
.stat-n.blue { color: #1a3a7e; }

/* ── Panels ── */
.panel {
  background: #fff;
  border: 1px solid #e0e4ea;
  border-radius: 8px;
  margin-bottom: 20px;
  overflow: hidden;
}
.panel-header {
  padding: 12px 18px;
  border-bottom: 1px solid #e8eaef;
  font-weight: 700;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #444;
  background: #fafbfc;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-body { padding: 18px; }

/* ── Tables ── */
.adm-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.adm-table th {
  background: #f4f6f9;
  padding: 9px 12px;
  text-align: left;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #666;
  border-bottom: 1px solid #e0e4ea;
  white-space: nowrap;
}
.adm-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f2f5;
  vertical-align: middle;
}
.adm-table tr:last-child td { border-bottom: none; }
.adm-table tr:hover td { background: #fafbfc; }

/* ── Badges ── */
.badge {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
}
.badge-dl   { background: #e0f5e8; color: #1a5e30; }
.badge-pend { background: #fff0dc; color: #8b4200; }
.badge-unres{ background: #f0e8ff; color: #4a1a8b; }
.badge-en   { background: #e8f0ff; color: #1a3a8b; }
.badge-hi   { background: #fff0e0; color: #8b4000; }
.badge-parsed { background: #e0f5e8; color: #1a5e30; }
.badge-unparsed { background: #fde8e8; color: #8b1a1a; }

/* ── Buttons ── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 34px; padding: 0 16px;
  border: none; border-radius: 6px;
  font-size: 0.82rem; font-weight: 600;
  cursor: pointer; font-family: inherit;
  transition: all 0.15s;
}
.btn-primary { background: #1a4a2e; color: #fff; }
.btn-primary:hover { background: #0f3020; }
.btn-danger { background: #b41a1a; color: #fff; }
.btn-danger:hover { background: #8b1010; }
.btn-ghost { background: transparent; color: #1a4a2e; border: 1px solid #1a4a2e; }
.btn-ghost:hover { background: #1a4a2e; color: #fff; }
.btn-sm { height: 26px; padding: 0 10px; font-size: 0.72rem; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Forms ── */
.form-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 16px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.4px; color: #666; font-weight: 600; }
.form-control {
  height: 34px; padding: 0 10px;
  border: 1px solid #d8dce4; border-radius: 6px;
  font-size: 0.82rem; font-family: inherit;
  background: #fff; color: #1a1a1a;
  outline: none; transition: border-color 0.15s;
}
.form-control:focus { border-color: #2a6a3a; }
select.form-control { padding-right: 28px; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath fill='%23888' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center; }

/* Multi-select: checkboxes list */
.check-group { display: flex; flex-wrap: wrap; gap: 8px; }
.check-group label {
  display: flex; align-items: center; gap: 5px;
  font-size: 0.78rem; font-weight: 500; color: #333;
  background: #f4f6f9; border: 1px solid #e0e4ea;
  border-radius: 4px; padding: 4px 10px; cursor: pointer;
  transition: all 0.15s; text-transform: none; letter-spacing: 0;
}
.check-group input[type=checkbox] { width: 14px; height: 14px; accent-color: #1a4a2e; }
.check-group label:has(input:checked) { background: #e0f5e8; border-color: #2a6a3a; color: #1a4a2e; }

/* ── Terminal log ── */
.log-terminal {
  background: #0d1117;
  color: #c9d1d9;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.78rem;
  border-radius: 6px;
  padding: 14px 16px;
  height: 340px;
  overflow-y: auto;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-terminal .log-done  { color: #3fb950; font-weight: 700; }
.log-terminal .log-error { color: #f85149; font-weight: 700; }
.log-terminal .log-warn  { color: #d29922; }
.log-terminal .log-info  { color: #58a6ff; }

/* ── Progress bar ── */
.progress-bar-wrap { background: #e0e4ea; border-radius: 4px; height: 6px; overflow: hidden; margin: 8px 0; }
.progress-bar-fill { background: #2a6a3a; height: 100%; transition: width 0.3s; border-radius: 4px; }

/* ── Two-col grid ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.three-col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col, .three-col { grid-template-columns: 1fr; } }

/* ── Pagination ── */
.pagination { display: flex; align-items: center; gap: 6px; padding: 14px 18px; border-top: 1px solid #e8eaef; }
.pagination .info { font-size: 0.78rem; color: #888; flex: 1; }
.page-btn {
  width: 30px; height: 30px; border: 1px solid #e0e4ea; background: #fff;
  border-radius: 4px; cursor: pointer; font-size: 0.78rem; color: #444;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.page-btn:hover { border-color: #2a6a3a; color: #2a6a3a; }
.page-btn.active { background: #1a4a2e; color: #fff; border-color: #1a4a2e; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Filters ── */
.filter-bar {
  background: #f4f6f9;
  border-bottom: 1px solid #e0e4ea;
  padding: 12px 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
}

/* ── Job status indicator ── */
.job-indicator {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 0.75rem; font-weight: 600;
}
.job-dot {
  width: 8px; height: 8px; border-radius: 50%;
  flex-shrink: 0;
}
.job-dot.running { background: #f9a825; animation: pulse 1s infinite; }
.job-dot.done    { background: #2ea043; }
.job-dot.error   { background: #f85149; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* ── Empty state ── */
.empty { text-align: center; padding: 40px; color: #aaa; }
.empty .icon { font-size: 2rem; margin-bottom: 8px; }

/* ── Scrollable table wrapper ── */
.table-wrap { overflow-x: auto; }
</style>
</head>
<body>

<header class="adm-header">
  <div class="adm-logo">ParamaSrota <span>Admin</span></div>
  <a href="/" class="adm-back">← Back to site</a>
</header>

<div class="adm-tabs">
  <a href="/admin/"        class="{{ 'active' if active_tab == 'dashboard' }}">📊 Dashboard</a>
  <a href="/admin/catalog" class="{{ 'active' if active_tab == 'catalog'   }}">📋 Catalog</a>
  <a href="/admin/scraper" class="{{ 'active' if active_tab == 'scraper'   }}">🕷️ Scraper</a>
  <a href="/admin/parser"  class="{{ 'active' if active_tab == 'parser'    }}">⚙️ Parser</a>
</div>

<div class="adm-body">
  {% block content %}{% endblock %}
</div>

<script>
// Shared utility: format a log line with colour spans
function fmtLogLine(line) {
  if (!line) return '';
  const esc = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  if (/error|fatal|failed|exception/i.test(esc)) return `<span class="log-error">${esc}</span>`;
  if (/warn|⚠/i.test(esc))                        return `<span class="log-warn">${esc}</span>`;
  if (/✓|done|success|complete/i.test(esc))        return `<span class="log-done">${esc}</span>`;
  if (/→|info|starting|phase/i.test(esc))          return `<span class="log-info">${esc}</span>`;
  return esc;
}

// Poll a job and stream lines into a terminal div
function streamJob(jobId, termEl, statusEl, doneCallback) {
  let source = new EventSource('/admin/api/stream/' + jobId);
  source.onmessage = function(e) {
    const line = e.data;
    if (line === '[DONE]' || line === '[ERROR]') {
      source.close();
      if (statusEl) {
        const ok = line === '[DONE]';
        statusEl.innerHTML = `<span class="job-indicator"><span class="job-dot ${ok?'done':'error'}"></span>${ok?'Completed':'Failed'}</span>`;
      }
      if (doneCallback) doneCallback(line === '[DONE]');
      return;
    }
    termEl.innerHTML += fmtLogLine(line) + '\n';
    termEl.scrollTop = termEl.scrollHeight;
  };
  source.onerror = function() {
    source.close();
    termEl.innerHTML += '<span class="log-error">Connection lost.</span>\n';
  };
  return source;
}
</script>

{% block extra_js %}{% endblock %}
</body>
</html>"""


# ── Dashboard ─────────────────────────────────────────────────────────────────

_DASHBOARD_TMPL = _ADMIN_BASE.replace(
    "{% block content %}{% endblock %}",
    """{% block content %}
<div class="stat-row">
  <div class="stat-card"><div class="stat-n">{{ s.total }}</div><div class="stat-l">Catalog Items</div></div>
  <div class="stat-card"><div class="stat-n green">{{ s.downloaded }}</div><div class="stat-l">Downloaded</div></div>
  <div class="stat-card"><div class="stat-n orange">{{ s.ready_to_dl }}</div><div class="stat-l">Ready to DL</div></div>
  <div class="stat-card"><div class="stat-n blue">{{ s.unresolved }}</div><div class="stat-l">Unresolved</div></div>
  <div class="stat-card"><div class="stat-n">{{ s.registered }}</div><div class="stat-l">Registered PDFs</div></div>
  <div class="stat-card"><div class="stat-n">{{ s.statements }}</div><div class="stat-l">Statements</div></div>
</div>

<div class="two-col">
  <div>
    <div class="panel">
      <div class="panel-header">Recent Downloads</div>
      {% if s.recent_downloads %}
      <div class="table-wrap">
      <table class="adm-table">
        <thead><tr><th>Date</th><th>Title</th><th>Collection</th><th>Lang</th><th>Size</th><th>When</th></tr></thead>
        <tbody>
        {% for r in s.recent_downloads %}
        <tr>
          <td style="white-space:nowrap;">{{ r.item_date or '—' }}</td>
          <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{{ r.title or '' }}">{{ (r.title or '—')[:55] }}</td>
          <td style="font-size:0.72rem;color:#888;">{{ r.collection_name or '—' }}</td>
          <td>{% if r.language %}<span class="badge badge-{{ 'en' if r.language == 'english' else 'hi' }}">{{ r.language[:2].upper() }}</span>{% else %}—{% endif %}</td>
          <td style="white-space:nowrap;color:#888;font-size:0.72rem;">{{ r.file_size_kb|default(0,true) }} KB</td>
          <td style="white-space:nowrap;color:#888;font-size:0.72rem;">{{ (r.downloaded_at or '')[:16] }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
      {% else %}
      <div class="empty"><div class="icon">📂</div><div>No downloads yet</div></div>
      {% endif %}
    </div>
  </div>

  <div>
    <div class="panel">
      <div class="panel-header">By Collection</div>
      <div class="table-wrap">
      <table class="adm-table">
        <thead><tr><th>Collection</th><th>Total</th><th>Downloaded</th></tr></thead>
        <tbody>
        {% for r in s.by_collection %}
        <tr>
          <td>{{ r.collection_name }}</td>
          <td style="text-align:right;">{{ r.n }}</td>
          <td style="text-align:right;">{{ r.dl or 0 }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
    </div>

    <div class="panel" style="margin-top:20px;">
      <div class="panel-header">Top Debate Types</div>
      <div class="table-wrap">
      <table class="adm-table">
        <thead><tr><th>Type</th><th>Items</th></tr></thead>
        <tbody>
        {% for r in s.by_debate_type %}
        <tr>
          <td style="font-size:0.78rem;">{{ r.debate_type }}</td>
          <td style="text-align:right;">{{ r.n }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
    </div>
  </div>
</div>
{% endblock %}"""
).replace("{% block extra_js %}{% endblock %}", "")


@admin_bp.route("/")
@admin_bp.route("")
def dashboard():
    s = _catalog_stats()
    return render_template_string(_DASHBOARD_TMPL, active_tab="dashboard", s=s)


# ── Catalog browser ───────────────────────────────────────────────────────────

_CATALOG_TMPL = _ADMIN_BASE.replace(
    "{% block content %}{% endblock %}",
    """{% block content %}
<div class="panel">
  <div class="filter-bar" id="filter-bar">
    <div class="form-group">
      <label>Collection</label>
      <select class="form-control" id="f-collection" onchange="loadCatalog(1)">
        <option value="">All</option>
        {% for c in filter_opts.collections %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>Language</label>
      <select class="form-control" id="f-lang" onchange="loadCatalog(1)">
        <option value="">All</option>
        {% for l in filter_opts.languages %}<option value="{{ l }}">{{ l }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>Status</label>
      <select class="form-control" id="f-status" onchange="loadCatalog(1)">
        <option value="">All</option>
        <option value="downloaded">Downloaded</option>
        <option value="pending">Pending (resolved)</option>
        <option value="unresolved">Unresolved</option>
      </select>
    </div>
    <div class="form-group">
      <label>Debate Type</label>
      <select class="form-control" id="f-dtype" onchange="loadCatalog(1)">
        <option value="">All</option>
        {% for dt in filter_opts.debate_types %}<option value="{{ dt }}">{{ dt }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>From Date</label>
      <input class="form-control" type="date" id="f-from" oninput="loadCatalog(1)" style="width:140px;">
    </div>
    <div class="form-group">
      <label>To Date</label>
      <input class="form-control" type="date" id="f-to" oninput="loadCatalog(1)" style="width:140px;">
    </div>
    <div class="form-group">
      <label>Search title/type</label>
      <input class="form-control" type="text" id="f-search" placeholder="keyword…" oninput="debounce(()=>loadCatalog(1),350)" style="width:200px;">
    </div>
  </div>

  <div class="table-wrap" id="catalog-wrap">
    <div class="empty"><div class="icon">⏳</div><div>Loading…</div></div>
  </div>

  <div class="pagination" id="catalog-pagination" style="display:none;">
    <span class="info" id="pg-info"></span>
    <button class="page-btn" id="pg-prev" onclick="changePage(-1)">‹</button>
    <span id="pg-pages"></span>
    <button class="page-btn" id="pg-next" onclick="changePage(1)">›</button>
  </div>
</div>
{% endblock %}""",
).replace(
    "{% block extra_js %}{% endblock %}",
    """{% block extra_js %}
<script>
let _page = 1;
let _total = 0;
const PER_PAGE = 40;
let _debTimer = null;

function debounce(fn, ms) {
  clearTimeout(_debTimer);
  _debTimer = setTimeout(fn, ms);
}

function loadCatalog(page) {
  _page = page || _page;
  const params = new URLSearchParams({
    page: _page,
    per_page: PER_PAGE,
    collection: document.getElementById('f-collection').value,
    language:   document.getElementById('f-lang').value,
    status:     document.getElementById('f-status').value,
    debate_type:document.getElementById('f-dtype').value,
    from_date:  document.getElementById('f-from').value,
    to_date:    document.getElementById('f-to').value,
    search:     document.getElementById('f-search').value,
  });
  fetch('/admin/api/catalog?' + params)
    .then(r => r.json())
    .then(data => {
      _total = data.total;
      renderTable(data.rows);
      renderPagination(data.total, data.page, data.per_page);
    });
}

function renderTable(rows) {
  const wrap = document.getElementById('catalog-wrap');
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty"><div class="icon">🔍</div><div>No results</div></div>';
    return;
  }
  let html = `<table class="adm-table">
    <thead><tr>
      <th>Doc ID</th><th>Date</th><th>Title</th><th>Collection</th>
      <th>Lang</th><th>Type</th><th>Session</th><th>Size</th><th>Status</th>
    </tr></thead><tbody>`;
  for (const r of rows) {
    const status = r.downloaded
      ? '<span class="badge badge-dl">Downloaded</span>'
      : r.filename
        ? '<span class="badge badge-pend">Pending</span>'
        : '<span class="badge badge-unres">Unresolved</span>';
    const lang = r.language
      ? `<span class="badge badge-${r.language==='english'?'en':'hi'}">${r.language.substring(0,2).toUpperCase()}</span>`
      : '—';
    const title = (r.title||'').substring(0,60) + (r.title && r.title.length > 60 ? '…' : '');
    const session = r.session_no_raw ? `${r.lok_sabha_no || '18'}/${r.session_no_raw}` : '—';
    const size = r.file_size_kb ? `${r.file_size_kb} KB` : '—';
    html += `<tr>
      <td><a href="https://eparlib.sansad.in/handle/123456789/${r.doc_id}" target="_blank" style="color:#1a3a8b;font-family:monospace;font-size:0.78rem;">${r.doc_id}</a></td>
      <td style="white-space:nowrap;">${r.item_date||'—'}</td>
      <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${(r.title||'').replace(/"/g,'&quot;')}">${title||'—'}</td>
      <td style="font-size:0.72rem;color:#888;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.collection_name||'—'}</td>
      <td>${lang}</td>
      <td style="font-size:0.72rem;color:#666;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${(r.debate_type||'').replace(/"/g,'&quot;')}">${r.debate_type||'—'}</td>
      <td style="white-space:nowrap;font-size:0.78rem;">${session}</td>
      <td style="white-space:nowrap;color:#888;font-size:0.72rem;">${size}</td>
      <td>${status}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function renderPagination(total, page, perPage) {
  const pages = Math.ceil(total / perPage);
  const info  = `${((page-1)*perPage)+1}–${Math.min(page*perPage, total)} of ${total}`;
  document.getElementById('pg-info').textContent = info;
  document.getElementById('pg-prev').disabled = page <= 1;
  document.getElementById('pg-next').disabled = page >= pages;
  // Show up to 5 page buttons
  let btns = '';
  const start = Math.max(1, page - 2);
  const end   = Math.min(pages, start + 4);
  for (let i = start; i <= end; i++) {
    btns += `<button class="page-btn ${i===page?'active':''}" onclick="loadCatalog(${i})">${i}</button>`;
  }
  document.getElementById('pg-pages').innerHTML = btns;
  document.getElementById('catalog-pagination').style.display = 'flex';
}

function changePage(delta) {
  const pages = Math.ceil(_total / PER_PAGE);
  _page = Math.max(1, Math.min(pages, _page + delta));
  loadCatalog(_page);
}

// Load on page init
loadCatalog(1);
</script>
{% endblock %}""",
)


@admin_bp.route("/catalog")
def catalog():
    filter_opts = _get_distinct_filter_values()
    return render_template_string(_CATALOG_TMPL, active_tab="catalog", filter_opts=filter_opts)


@admin_bp.route("/api/catalog")
def api_catalog():
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 40))
    filters  = {
        "collection":  request.args.get("collection", ""),
        "language":    request.args.get("language", ""),
        "status":      request.args.get("status", ""),
        "from_date":   request.args.get("from_date", ""),
        "to_date":     request.args.get("to_date", ""),
        "debate_type": request.args.get("debate_type", ""),
        "search":      request.args.get("search", ""),
    }
    rows, total = _get_catalog_page(page, per_page, filters)
    return jsonify({"rows": rows, "total": total, "page": page, "per_page": per_page})


# ── Scraper control ───────────────────────────────────────────────────────────

_SCRAPER_TMPL = _ADMIN_BASE.replace(
    "{% block content %}{% endblock %}",
    """{% block content %}
<div class="two-col">

  <!-- Run new job -->
  <div>
    <div class="panel">
      <div class="panel-header">Run Playwright Scraper</div>
      <div class="panel-body">

        <div class="form-group" style="margin-bottom:14px;">
          <label>Phases</label>
          <div class="check-group">
            <label><input type="checkbox" id="ph-catalog" checked> --catalog</label>
            <label><input type="checkbox" id="ph-resolve"> --resolve</label>
            <label><input type="checkbox" id="ph-download"> --download</label>
          </div>
        </div>

        <div class="form-group" style="margin-bottom:14px;">
          <label>Collections</label>
          <div class="check-group" id="collection-checks">
            <label><input type="checkbox" name="col" value="debates" checked> Debates</label>
            <label><input type="checkbox" name="col" value="presidential"> Presidential</label>
            <label><input type="checkbox" name="col" value="budget"> Budget</label>
            <label><input type="checkbox" name="col" value="debates_ucd"> UCD</label>
            <label><input type="checkbox" name="col" value="pm_speeches"> PM Speeches</label>
            <label><input type="checkbox" name="col" value="resume"> Resume</label>
            <label><input type="checkbox" name="col" value="committee"> Committee</label>
            <label><input type="checkbox" name="col" value="questions_p1"> Questions P1</label>
            <label><input type="checkbox" name="col" value="questions_p2"> Questions P2</label>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Limit (items)</label>
            <input class="form-control" type="number" id="sc-limit" value="50" min="1" max="500" style="width:100px;">
          </div>
          <div class="form-group">
            <label>From Date</label>
            <input class="form-control" type="date" id="sc-from" style="width:150px;">
          </div>
          <div class="form-group">
            <label>To Date</label>
            <input class="form-control" type="date" id="sc-to" style="width:150px;">
          </div>
        </div>

        <button class="btn btn-primary" id="run-btn" onclick="runScraper()">▶ Run Scraper</button>
        <span id="run-status" style="margin-left:12px;"></span>
      </div>
    </div>

    <!-- Past jobs -->
    <div class="panel" style="margin-top:20px;">
      <div class="panel-header">
        Job History
        <button class="btn btn-ghost btn-sm" onclick="loadJobs()">↻ Refresh</button>
      </div>
      <div id="jobs-list">
        <div class="empty"><div class="icon">📋</div><div>No jobs yet</div></div>
      </div>
    </div>
  </div>

  <!-- Live log -->
  <div>
    <div class="panel">
      <div class="panel-header">
        Live Log
        <span id="log-status"></span>
      </div>
      <div class="panel-body" style="padding:0;">
        <div class="log-terminal" id="log-terminal">Waiting for job…
</div>
      </div>
    </div>
  </div>
</div>
{% endblock %}""",
).replace(
    "{% block extra_js %}{% endblock %}",
    """{% block extra_js %}
<script>
let _activeSource = null;

function runScraper() {
  const phases = [];
  if (document.getElementById('ph-catalog').checked)  phases.push('catalog');
  if (document.getElementById('ph-resolve').checked)   phases.push('resolve');
  if (document.getElementById('ph-download').checked)  phases.push('download');
  if (!phases.length) { alert('Select at least one phase.'); return; }

  const cols = Array.from(document.querySelectorAll('input[name=col]:checked')).map(el=>el.value);
  const limit = document.getElementById('sc-limit').value;
  const from  = document.getElementById('sc-from').value;
  const to    = document.getElementById('sc-to').value;

  fetch('/admin/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type:'scraper', phases, collections:cols, limit, from_date:from, to_date:to}),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert(data.error); return; }
    startStream(data.job_id);
    loadJobs();
  });
}

function startStream(jobId) {
  if (_activeSource) _activeSource.close();
  const term = document.getElementById('log-terminal');
  const status = document.getElementById('log-status');
  term.innerHTML = '';
  status.innerHTML = '<span class="job-indicator"><span class="job-dot running"></span>Running…</span>';
  document.getElementById('run-btn').disabled = true;

  _activeSource = streamJob(jobId, term, status, (ok) => {
    document.getElementById('run-btn').disabled = false;
    loadJobs();
  });
}

function loadJobs() {
  fetch('/admin/api/jobs')
    .then(r => r.json())
    .then(jobs => {
      const el = document.getElementById('jobs-list');
      if (!jobs.length) {
        el.innerHTML = '<div class="empty"><div class="icon">📋</div><div>No jobs yet</div></div>';
        return;
      }
      let html = '<table class="adm-table"><thead><tr><th>ID</th><th>Command</th><th>Status</th><th>Started</th><th>Action</th></tr></thead><tbody>';
      for (const j of jobs) {
        const dot = `<span class="job-indicator"><span class="job-dot ${j.status}"></span>${j.status}</span>`;
        html += `<tr>
          <td style="font-family:monospace;font-size:0.75rem;">${j.id}</td>
          <td style="font-size:0.72rem;color:#666;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${j.cmd}">${j.cmd.substring(0,80)}</td>
          <td>${dot}</td>
          <td style="font-size:0.72rem;color:#888;">${j.started_at.substring(0,16)}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="viewJob('${j.id}')">View log</button></td>
        </tr>`;
      }
      html += '</tbody></table>';
      el.innerHTML = html;
    });
}

function viewJob(jobId) {
  fetch('/admin/api/jobs/' + jobId)
    .then(r => r.json())
    .then(job => {
      const term = document.getElementById('log-terminal');
      term.innerHTML = job.log.map(fmtLogLine).join('\n') + '\n';
      term.scrollTop = term.scrollHeight;
      const status = document.getElementById('log-status');
      status.innerHTML = `<span class="job-indicator"><span class="job-dot ${job.status}"></span>${job.status}</span>`;
      if (job.status === 'running') startStream(jobId);
    });
}

loadJobs();
</script>
{% endblock %}""",
)


@admin_bp.route("/scraper")
def scraper():
    return render_template_string(_SCRAPER_TMPL, active_tab="scraper")


# ── Parser control ────────────────────────────────────────────────────────────

_PARSER_TMPL = _ADMIN_BASE.replace(
    "{% block content %}{% endblock %}",
    """{% block content %}
<div class="two-col">

  <!-- Control panel -->
  <div>
    <div class="panel">
      <div class="panel-header">Run Parser</div>
      <div class="panel-body">
        <p style="font-size:0.82rem;color:#666;margin-bottom:14px;">
          Parse all registered PDFs that have no statements yet.
          Enable translation to run Sarvam AI on Hindi content
          (requires <code>SARVAM_API_KEY</code> in environment).
        </p>

        <div class="form-group" style="margin-bottom:14px;">
          <label>Options</label>
          <div class="check-group">
            <label><input type="checkbox" id="opt-translate"> --translate (Sarvam AI)</label>
          </div>
        </div>

        <button class="btn btn-primary" id="parse-btn" onclick="runParser()">▶ Run Parser</button>
        <span id="parse-status" style="margin-left:12px;"></span>
      </div>
    </div>

    <!-- PDFs status -->
    <div class="panel" style="margin-top:20px;">
      <div class="panel-header">
        Registered PDFs
        <a href="/admin/api/refresh-parse" class="btn btn-ghost btn-sm" onclick="refreshParse(event)">↻ Refresh</a>
      </div>
      <div class="table-wrap" id="parse-table">
        <div class="empty"><div class="icon">⏳</div><div>Loading…</div></div>
      </div>
    </div>
  </div>

  <!-- Live log -->
  <div>
    <div class="panel">
      <div class="panel-header">
        Live Log
        <span id="plog-status"></span>
      </div>
      <div class="panel-body" style="padding:0;">
        <div class="log-terminal" id="plog-terminal">Waiting for job…
</div>
      </div>
    </div>
  </div>
</div>
{% endblock %}""",
).replace(
    "{% block extra_js %}{% endblock %}",
    """{% block extra_js %}
<script>
let _pSource = null;

function loadParsePdfs() {
  fetch('/admin/api/parse-pdfs')
    .then(r => r.json())
    .then(pdfs => {
      const el = document.getElementById('parse-table');
      if (!pdfs.length) {
        el.innerHTML = '<div class="empty"><div class="icon">📂</div><div>No PDFs registered</div></div>';
        return;
      }
      let html = '<table class="adm-table"><thead><tr><th>Filename</th><th>Date</th><th>Session</th><th>Lang</th><th>Statements</th><th>Status</th></tr></thead><tbody>';
      for (const p of pdfs) {
        const lang  = `<span class="badge badge-${p.language==='english'?'en':'hi'}">${(p.language||'?').substring(0,2).toUpperCase()}</span>`;
        const badge = p.stmt_count > 0
          ? `<span class="badge badge-parsed">${p.stmt_count} stmts</span>`
          : `<span class="badge badge-unparsed">Unparsed</span>`;
        html += `<tr>
          <td style="font-family:monospace;font-size:0.75rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${p.filename}</td>
          <td style="white-space:nowrap;">${p.sitting_date||'—'}</td>
          <td style="white-space:nowrap;">${p.session_no||'—'}</td>
          <td>${lang}</td>
          <td style="text-align:right;">${p.stmt_count}</td>
          <td>${badge}</td>
        </tr>`;
      }
      html += '</tbody></table>';
      el.innerHTML = html;
    });
}

function refreshParse(e) {
  e && e.preventDefault();
  loadParsePdfs();
}

function runParser() {
  const translate = document.getElementById('opt-translate').checked;
  fetch('/admin/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type:'parser', translate}),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { alert(data.error); return; }
    if (_pSource) _pSource.close();
    const term = document.getElementById('plog-terminal');
    const status = document.getElementById('plog-status');
    term.innerHTML = '';
    status.innerHTML = '<span class="job-indicator"><span class="job-dot running"></span>Running…</span>';
    document.getElementById('parse-btn').disabled = true;
    _pSource = streamJob(data.job_id, term, status, (ok) => {
      document.getElementById('parse-btn').disabled = false;
      loadParsePdfs();
    });
  });
}

loadParsePdfs();
</script>
{% endblock %}""",
)


@admin_bp.route("/parser")
def parser():
    return render_template_string(_PARSER_TMPL, active_tab="parser")


# ── API — stats ───────────────────────────────────────────────────────────────

@admin_bp.route("/api/stats")
def api_stats():
    return jsonify(_catalog_stats())


@admin_bp.route("/api/parse-pdfs")
def api_parse_pdfs():
    return jsonify(_get_pending_parse())


# ── API — run job ─────────────────────────────────────────────────────────────

@admin_bp.route("/api/run", methods=["POST"])
def api_run():
    """Start a scraper or parser job. Returns {job_id}."""
    data = request.get_json(force=True) or {}
    job_type = data.get("type", "scraper")

    # Load env from .env file if present
    env_file = _ROOT / ".env"
    extra_env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                extra_env[k.strip()] = v.strip()

    if job_type == "scraper":
        phases      = data.get("phases", ["catalog"])
        collections = data.get("collections", [])
        limit       = str(data.get("limit") or 50)
        from_date   = data.get("from_date", "")
        to_date     = data.get("to_date", "")

        scraper_py = _ROOT / "scrapers" / "parliament" / "playwright_scraper.py"
        if not scraper_py.exists():
            return jsonify({"error": f"Scraper not found: {scraper_py}"}), 404

        cmd = [sys.executable, str(scraper_py)]
        for phase in phases:
            cmd.append(f"--{phase}")
        if collections:
            cmd.extend(["--collections"] + collections)
        if limit:
            cmd.extend(["--limit", limit])
        if from_date:
            cmd.extend(["--from", from_date])
        if to_date:
            cmd.extend(["--to", to_date])

    elif job_type == "parser":
        translate = data.get("translate", False)
        main_py   = _ROOT / "main.py"
        if not main_py.exists():
            return jsonify({"error": f"main.py not found: {main_py}"}), 404

        cmd = [sys.executable, str(main_py), "--parse-only"]
        if translate:
            cmd.append("--translate")

    else:
        return jsonify({"error": f"Unknown job type: {job_type}"}), 400

    job_id = _start_job(cmd, cwd=_ROOT, env=extra_env if extra_env else None)
    return jsonify({"job_id": job_id, "cmd": " ".join(cmd)})


# ── API — job management ──────────────────────────────────────────────────────

@admin_bp.route("/api/jobs")
def api_jobs():
    """List all jobs (most recent first)."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    jobs.sort(key=lambda j: j["started_at"], reverse=True)
    return jsonify([
        {k: v for k, v in j.items() if k not in ("process",)}
        for j in jobs
    ])


@admin_bp.route("/api/jobs/<job_id>")
def api_job(job_id: str):
    """Return full job details including log lines."""
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({k: v for k, v in job.items() if k not in ("process",)})


# ── API — SSE log stream ──────────────────────────────────────────────────────

@admin_bp.route("/api/stream/<job_id>")
def api_stream(job_id: str):
    """
    Server-Sent Events stream for a running job's stdout.
    Sends one line per event. Sends [DONE] or [ERROR] when complete.
    """
    job = _jobs.get(job_id)
    if not job:
        def _not_found():
            yield "data: Job not found\n\n"
        return Response(stream_with_context(_not_found()), mimetype="text/event-stream")

    def _generate():
        sent = 0
        while True:
            lines = job["log"]
            while sent < len(lines):
                line = lines[sent].replace("\n", " ")
                yield f"data: {line}\n\n"
                sent += 1
            if job["status"] in ("done", "error"):
                terminal = "[DONE]" if job["status"] == "done" else "[ERROR]"
                yield f"data: {terminal}\n\n"
                break
            time.sleep(0.15)

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
