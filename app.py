"""
app.py — Sansad Search UI
Run: python app.py
Opens at: http://localhost:5100

Search is powered entirely by SQLite FTS5 — no LLM involved.
"""

from flask import Flask, jsonify, request, render_template_string
from db import get_connection

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sansad Search</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f0; color: #1a1a1a; min-height: 100vh; }

  header { background: #1a3a2a; color: #fff; padding: 20px 32px;
           display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 1.4rem; font-weight: 600; letter-spacing: -0.3px; }
  header span { font-size: 0.85rem; opacity: 0.6; }
  .ashoka { font-size: 1.8rem; }

  .search-bar { background: #fff; border-bottom: 1px solid #e0e0d8;
                padding: 20px 32px; display: flex; gap: 12px; flex-wrap: wrap;
                align-items: flex-end; position: sticky; top: 0; z-index: 10;
                box-shadow: 0 2px 8px rgba(0,0,0,0.06); }

  .field { display: flex; flex-direction: column; gap: 5px; }
  .field label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
                 letter-spacing: 0.5px; color: #666; }
  input, select { height: 38px; padding: 0 12px; border: 1px solid #d0d0c8;
                  border-radius: 6px; font-size: 0.9rem; background: #fafaf8;
                  outline: none; transition: border 0.15s; }
  input:focus, select:focus { border-color: #2a6a4a; background: #fff; }
  input[type="text"] { width: 320px; }
  select { width: 240px; }
  select.narrow { width: 160px; }

  .btn { height: 38px; padding: 0 20px; border: none; border-radius: 6px;
         font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: 0.15s; }
  .btn-primary { background: #2a6a4a; color: #fff; }
  .btn-primary:hover { background: #1a4a3a; }
  .btn-secondary { background: #eee; color: #555; }
  .btn-secondary:hover { background: #e0e0d8; }

  .results-meta { padding: 14px 32px; font-size: 0.85rem; color: #666;
                  border-bottom: 1px solid #e8e8e0; background: #fafaf8; }
  .results-meta strong { color: #1a1a1a; }

  .results { padding: 20px 32px; display: flex; flex-direction: column; gap: 12px; }

  .card { background: #fff; border: 1px solid #e8e8e0; border-radius: 10px;
          padding: 18px 20px; transition: box-shadow 0.15s; }
  .card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }

  .card-header { display: flex; align-items: flex-start;
                 justify-content: space-between; gap: 12px; margin-bottom: 10px; }
  .speaker { font-weight: 700; font-size: 0.95rem; color: #1a3a2a; }
  .meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .badge { font-size: 0.72rem; font-weight: 600; padding: 3px 8px;
           border-radius: 20px; text-transform: uppercase; letter-spacing: 0.3px; }
  .badge-speech       { background: #e8f4ee; color: #2a6a4a; }
  .badge-question     { background: #e8eef8; color: #2a4a8a; }
  .badge-answer       { background: #f8f0e8; color: #8a4a2a; }
  .badge-ruling       { background: #f0e8f8; color: #6a2a8a; }
  .badge-interruption { background: #f5f5ee; color: #666; }
  .date-chip { font-size: 0.78rem; color: #888; background: #f5f5ee;
               padding: 3px 8px; border-radius: 20px; }
  .session-chip { font-size: 0.72rem; color: #aaa; }

  .text { font-size: 0.88rem; line-height: 1.65; color: #333;
          border-top: 1px solid #f0f0e8; padding-top: 10px; }
  .text.collapsed { display: -webkit-box; -webkit-line-clamp: 3;
                    -webkit-box-orient: vertical; overflow: hidden; }
  .expand-btn { font-size: 0.78rem; color: #2a6a4a; cursor: pointer;
                background: none; border: none; padding: 4px 0;
                margin-top: 6px; font-weight: 600; }
  .expand-btn:hover { text-decoration: underline; }

  .empty { text-align: center; padding: 64px 32px; color: #999; }
  .empty .icon { font-size: 3rem; margin-bottom: 12px; }
  .spinner { text-align: center; padding: 40px; color: #999; font-size: 0.9rem; }

  @media (max-width: 700px) {
    .search-bar { padding: 16px; }
    .results { padding: 16px; }
    input[type="text"], select { width: 100%; }
  }
</style>
</head>
<body>

<header>
  <span class="ashoka">⚖</span>
  <div>
    <h1>Sansad Debate Search</h1>
    <span>18th Lok Sabha — attributed statements database</span>
  </div>
</header>

<div class="search-bar">
  <div class="field">
    <label>Free-text search</label>
    <input type="text" id="q" placeholder="e.g. Vande Mataram, budget, education…" />
  </div>
  <div class="field">
    <label>Speaker</label>
    <select id="speaker">
      <option value="">All speakers</option>
    </select>
  </div>
  <div class="field">
    <label>Session</label>
    <select id="session" class="narrow">
      <option value="">All sessions</option>
      <option value="1">Session 1 (Jun–Jul 2024)</option>
      <option value="2">Session 2 (Jul–Aug 2024)</option>
      <option value="3">Winter 2024</option>
      <option value="4">Budget 2025</option>
      <option value="5">Monsoon 2025</option>
      <option value="6">Winter 2025</option>
    </select>
  </div>
  <div class="field">
    <label>Type</label>
    <select id="stype" class="narrow">
      <option value="">All types</option>
      <option value="speech">Speech</option>
      <option value="question">Question</option>
      <option value="answer">Answer</option>
      <option value="ruling">Ruling</option>
      <option value="interruption">Interruption</option>
    </select>
  </div>
  <div class="field" style="flex-direction:row;gap:8px;align-items:flex-end;">
    <button class="btn btn-primary" onclick="doSearch()">Search</button>
    <button class="btn btn-secondary" onclick="clearAll()">Clear</button>
  </div>
</div>

<div class="results-meta" id="meta" style="display:none"></div>
<div id="results">
  <div class="empty">
    <div class="icon">🏛️</div>
    <div>Search by speaker, keyword, or both</div>
  </div>
</div>

<script>
// ── Load speakers dropdown ───────────────────────────────────────────────────
fetch('/api/speakers').then(r => r.json()).then(data => {
  const sel = document.getElementById('speaker');
  data.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.name_normalized;
    opt.textContent = s.name + (s.stmt_count ? ` (${s.stmt_count})` : '');
    sel.appendChild(opt);
  });
});

// ── Enter key triggers search ────────────────────────────────────────────────
document.getElementById('q').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

// ── Search ───────────────────────────────────────────────────────────────────
function doSearch() {
  const q       = document.getElementById('q').value.trim();
  const speaker = document.getElementById('speaker').value;
  const session = document.getElementById('session').value;
  const stype   = document.getElementById('stype').value;

  document.getElementById('results').innerHTML =
    '<div class="spinner">Searching…</div>';
  document.getElementById('meta').style.display = 'none';

  const params = new URLSearchParams();
  if (q)       params.set('q', q);
  if (speaker) params.set('speaker', speaker);
  if (session) params.set('session', session);
  if (stype)   params.set('type', stype);

  fetch('/api/search?' + params).then(r => r.json()).then(render);
}

function clearAll() {
  document.getElementById('q').value = '';
  document.getElementById('speaker').value = '';
  document.getElementById('session').value = '';
  document.getElementById('stype').value = '';
  document.getElementById('results').innerHTML =
    '<div class="empty"><div class="icon">🏛️</div><div>Search by speaker, keyword, or both</div></div>';
  document.getElementById('meta').style.display = 'none';
}

// ── Render results ───────────────────────────────────────────────────────────
function render(data) {
  const meta = document.getElementById('meta');
  const out  = document.getElementById('results');

  if (!data.results || data.results.length === 0) {
    meta.style.display = 'none';
    out.innerHTML = '<div class="empty"><div class="icon">🔍</div><div>No statements found — try different terms</div></div>';
    return;
  }

  meta.style.display = 'block';
  meta.innerHTML = `Showing <strong>${data.results.length}</strong> of <strong>${data.total}</strong> statements`;

  const cards = data.results.map((r, i) => `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="speaker">${esc(r.speaker_raw)}</div>
          ${r.constituency ? `<div style="font-size:0.78rem;color:#888;margin-top:2px">${esc(r.constituency)}</div>` : ''}
        </div>
        <div class="meta">
          <span class="badge badge-${r.statement_type}">${r.statement_type}</span>
          <span class="date-chip">📅 ${r.sitting_date}</span>
          <span class="session-chip">Sess. ${r.session_no}</span>
          <span class="date-chip">${r.word_count} words</span>
        </div>
      </div>
      <div class="text collapsed" id="text-${i}">${esc(r.statement_text)}</div>
      <button class="expand-btn" id="btn-${i}" onclick="toggle(${i})">Show more ▼</button>
    </div>
  `).join('');

  out.innerHTML = `<div class="results">${cards}</div>`;
}

function toggle(i) {
  const el  = document.getElementById('text-' + i);
  const btn = document.getElementById('btn-' + i);
  if (el.classList.contains('collapsed')) {
    el.classList.remove('collapsed');
    btn.textContent = 'Show less ▲';
  } else {
    el.classList.add('collapsed');
    btn.textContent = 'Show more ▼';
  }
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/speakers")
def speakers():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT m.name, m.name_normalized, m.constituency,
               COUNT(s.id) as stmt_count
        FROM members m
        LEFT JOIN statements s ON s.member_id = m.id
        GROUP BY m.id
        ORDER BY stmt_count DESC, m.name ASC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/search")
def search():
    q       = request.args.get("q", "").strip()
    speaker = request.args.get("speaker", "").strip()
    session = request.args.get("session", "").strip()
    stype   = request.args.get("type", "").strip()
    limit   = int(request.args.get("limit", 50))

    conn = get_connection()
    c    = conn.cursor()

    if q:
        # FTS5 search — fast, no LLM
        sql = """
            SELECT
                s.speaker_raw, s.sitting_date, s.session_no,
                s.statement_type, s.statement_text, s.word_count,
                m.constituency, m.name_normalized
            FROM statements_fts
            JOIN statements s ON statements_fts.rowid = s.id
            JOIN members m    ON s.member_id = m.id
            WHERE statements_fts MATCH ?
        """
        params = [q]
    else:
        sql = """
            SELECT
                s.speaker_raw, s.sitting_date, s.session_no,
                s.statement_type, s.statement_text, s.word_count,
                m.constituency, m.name_normalized
            FROM statements s
            JOIN members m ON s.member_id = m.id
            WHERE 1=1
        """
        params = []

    if speaker:
        sql += " AND m.name_normalized LIKE ?"
        params.append(f"%{speaker}%")
    if session:
        sql += " AND s.session_no = ?"
        params.append(int(session))
    if stype:
        sql += " AND s.statement_type = ?"
        params.append(stype)

    # Get total count
    count_sql = f"SELECT COUNT(*) FROM ({sql})"
    c.execute(count_sql, params)
    total = c.fetchone()[0]

    sql += " ORDER BY s.sitting_date DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    return jsonify({"total": total, "results": rows})


if __name__ == "__main__":
    print("\n🏛  Sansad Search UI")
    print("   Open your browser at: http://localhost:5100\n")
    app.run(port=5100, debug=False)
