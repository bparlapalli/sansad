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


@draft_bp.route("/claims")
def claims():
    return _render(RESEARCH_DIR / "claims.md", "Claims and verification status", back="/draft")


@draft_bp.route("/wiki")
def wiki_index():
    return _render(RESEARCH_DIR / "wiki" / "INDEX.md", "Wiki", back="/draft")


@draft_bp.route("/wiki/<slug>")
def wiki_page(slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        abort(404)
    return _render(RESEARCH_DIR / "wiki" / f"{slug}.md", slug, back="/draft/wiki")
