"""
app/draft_bp.py — password-protected PRIVATE section: the Hyderabad draft post, claims/verification
status and wiki stubs.

  /draft/login          password form
  /draft                hub
  /draft/post           DRAFT post
  /draft/claims         every claim: grade, located passage, gap
  /draft/wiki           wiki index      /draft/wiki/<slug>   one page

The content is unverified research. It is NOT part of the public data: it is pushed separately
(push_research.py → POST /ingest/research) as a zip of markdown files and lives in a folder next
to the database, so — like the DB — it is wiped by a redeploy and re-pushed.

Access: OPEN by default — a hidden, unlinked, noindex URL meant for a handful of reviewers (founder's
decision, 2026-09-29; a proper protected site is planned). To lock it, set DRAFT_PASSWORD in the Render
dashboard (never in a file or the repo): every route then requires the shared password.
Not a substitute for real accounts.
"""
import hmac
import os
import re
import time
from pathlib import Path

from flask import (Blueprint, abort, make_response, redirect, render_template, request,
                   session, url_for)
from markdown_it import MarkdownIt

from core.db import DB_PATH

draft_bp = Blueprint("draft_bp", __name__, url_prefix="/draft")

# RESEARCH_DIR overrides the location (tests / local preview). Default: next to the DB.
RESEARCH_DIR = Path(os.getenv("RESEARCH_DIR") or (DB_PATH.parent / "research_private"))

# html=False: raw HTML in the source (scraped article text!) is shown as text, never executed.
_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

_fails: dict[str, list[float]] = {}     # ip -> recent failed-login times (in memory, per worker)
_MAX_FAILS, _WINDOW = 5, 300


def _password() -> str | None:
    return os.getenv("DRAFT_PASSWORD") or None


def _client_ip() -> str:
    # Render sits behind a proxy; the first X-Forwarded-For entry is the client.
    return (request.headers.get("X-Forwarded-For", request.remote_addr or "") or "").split(",")[0].strip()


def _locked_out(ip: str) -> bool:
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < _WINDOW]
    return len(_fails[ip]) >= _MAX_FAILS


@draft_bp.before_request
def _gate():
    if not _password():
        return None      # no DRAFT_PASSWORD configured → open (hidden URL, a few reviewers); set it to lock
    if request.endpoint in ("draft_bp.login",):
        return None
    if not session.get("draft_ok"):
        return redirect(url_for("draft_bp.login", next=request.path))
    return None


@draft_bp.after_request
def _no_cache_no_index(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@draft_bp.route("/login", methods=["GET", "POST"])
def login():
    if not _password():
        return redirect(url_for("draft_bp.hub"))
    error = None
    if request.method == "POST":
        ip = _client_ip()
        if _locked_out(ip):
            error = "Too many attempts. Wait a few minutes and try again."
        elif hmac.compare_digest((request.form.get("password") or "").encode(), _password().encode()):
            session.clear()
            session["draft_ok"] = True
            nxt = request.args.get("next", "")
            # only ever redirect inside this section
            return redirect(nxt if nxt.startswith("/draft") and not nxt.startswith("//") else url_for("draft_bp.hub"))
        else:
            _fails.setdefault(ip, []).append(time.time())
            error = "Wrong password."
    return render_template("draft_login.html", active_tab="draft", ticker_text=None, error=error)


@draft_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("draft_bp.login"))


def _render(md_path: Path, title: str, back: str | None = None):
    if not md_path.exists():
        abort(404)
    html = _md.render(md_path.read_text(encoding="utf-8"))
    # wiki pages link to each other as "x.md" or "../wiki/x.md" → our routes
    html = re.sub(r'href="(?:\.\./wiki/|wiki/)?([a-z0-9][a-z0-9-]*)\.md"',
                  lambda m: 'href="/draft/wiki"' if m.group(1) == "INDEX" or m.group(1) == "index"
                  else f'href="/draft/wiki/{m.group(1)}"', html)
    html = html.replace('<a href="http', '<a target="_blank" rel="noopener noreferrer" href="http')
    return render_template("draft_page.html", active_tab="draft", ticker_text=None,
                           title=title, body=html, back=back)


def _atlas_document(md_path: Path) -> dict[str, str]:
    """Render one private research document for the Editorial Atlas preview.

    The research bundle remains the only content source.  The public repository
    contains presentation code, but no copied research prose or figures.
    """
    if not md_path.exists():
        abort(404)
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), md_path.stem)
    intro = ""
    seen_title = False
    for line in lines:
        if line.startswith("# "):
            seen_title = True
            continue
        if seen_title and line.strip() and not line.startswith(("<!--", "-->", "---")):
            intro = re.sub(r"[*_`\[\]]", "", line.strip())
            break
    html = _md.render(text)
    html = re.sub(
        r'href="(?:\.\./)?wiki/data-([a-z0-9][a-z0-9-]*)\.md"',
        r'href="/draft/data/\1"', html)
    html = re.sub(
        r'href="data-([a-z0-9][a-z0-9-]*)\.md"',
        r'href="/draft/data/\1"', html)
    html = re.sub(
        r'src="(?:\.\./)?img/([a-z0-9][a-z0-9-]*)\.svg"',
        r'src="/draft/img/\1.svg"', html)
    html = html.replace('href="../post"', 'href="/draft/atlas"')
    html = html.replace('href="post"', 'href="/draft/atlas"')
    html = html.replace('href="claims"', 'href="/draft/claims"')
    html = html.replace('<a href="http', '<a target="_blank" rel="noopener noreferrer" href="http')
    return {"title": title, "intro": intro, "body": html}


def _atlas_datasets() -> list[dict[str, str | bool]]:
    datasets: list[dict[str, str | bool]] = []
    wiki_dir = RESEARCH_DIR / "wiki"
    if not wiki_dir.exists():
        return datasets
    for path in sorted(wiki_dir.glob("data-*.md")):
        slug = path.stem.removeprefix("data-")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            continue
        doc = _atlas_document(path)
        datasets.append({
            "slug": slug,
            "title": doc["title"],
            "intro": doc["intro"],
            "has_chart": (RESEARCH_DIR / "img" / f"{slug}.svg").exists(),
        })
    return datasets


@draft_bp.route("/")
def hub():
    have = {p: (RESEARCH_DIR / p).exists() for p in ("post.md", "claims.md", "wiki/INDEX.md")}
    pushed = None
    stamp = RESEARCH_DIR / "PUSHED_AT.txt"
    if stamp.exists():
        pushed = stamp.read_text(encoding="utf-8").strip()
    return render_template("draft_hub.html", active_tab="draft", ticker_text=None, have=have, pushed=pushed)


@draft_bp.route("/post")
def post():
    return _render(RESEARCH_DIR / "post.md", "Draft post", back="/draft")


@draft_bp.route("/atlas")
def atlas():
    doc = _atlas_document(RESEARCH_DIR / "post.md")
    return render_template("editorial_atlas_story.html", **doc)


@draft_bp.route("/data")
def data_hub():
    return render_template("editorial_dataset_hub.html", datasets=_atlas_datasets())


@draft_bp.route("/data/<slug>")
def data_analysis(slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        abort(404)
    doc = _atlas_document(RESEARCH_DIR / "wiki" / f"data-{slug}.md")
    chart_name = slug if (RESEARCH_DIR / "img" / f"{slug}.svg").exists() else None
    return render_template("editorial_analysis.html", chart_name=chart_name, slug=slug, **doc)


@draft_bp.route("/claims")
def claims():
    return _render(RESEARCH_DIR / "claims.md", "Claims and verification status", back="/draft")


@draft_bp.route("/wiki")
def wiki_index():
    return _render(RESEARCH_DIR / "wiki" / "INDEX.md", "Wiki", back="/draft")


@draft_bp.route("/img/<name>.svg")
def image(name):
    """Graphics pushed with the bundle (img/*.svg). Served as an image with a locked-down CSP, so even a
    direct visit can't run script; ingest also rejects SVGs containing script-like content."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        abort(404)
    path = RESEARCH_DIR / "img" / f"{name}.svg"
    if not path.exists():
        abort(404)
    resp = make_response(path.read_bytes())
    resp.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@draft_bp.route("/wiki/<slug>")
def wiki_page(slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        abort(404)
    return _render(RESEARCH_DIR / "wiki" / f"{slug}.md", slug, back="/draft/wiki")
