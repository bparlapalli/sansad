"""
app/ingest_bp.py — Receives the trimmed public.db pushed from the local
machine and swaps it in atomically. Machine-to-machine only: a bearer token
(INGEST_TOKEN env var), not the admin session login.

The full dataset never reaches this server — only whatever
parser/export_public_db.py chose to include (see push_public_db.py).
"""

import io
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, request, jsonify

from core.db import DB_PATH
from app.draft_bp import RESEARCH_DIR

ingest_bp = Blueprint("ingest_bp", __name__)


def _token_ok(req) -> bool:
    expected = os.getenv("INGEST_TOKEN")
    if not expected:
        return False  # refuse everything if no token is configured
    got = req.headers.get("Authorization", "")
    return got == f"Bearer {expected}"


def _looks_like_valid_db(path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("SELECT COUNT(*) FROM statements")
        conn.close()
        return True
    except sqlite3.Error:
        return False


@ingest_bp.route("/ingest/db", methods=["POST"])
def ingest_db():
    if not _token_ok(request):
        return jsonify({"error": "unauthorized"}), 401

    uploaded = request.files.get("db_file")
    if not uploaded:
        return jsonify({"error": "missing db_file"}), 400

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=str(DB_PATH.parent))
    tmp_path = Path(tmp_path)
    try:
        os.close(tmp_fd)
        uploaded.save(str(tmp_path))

        if not _looks_like_valid_db(tmp_path):
            tmp_path.unlink(missing_ok=True)
            return jsonify({"error": "uploaded file is not a valid statements DB"}), 400

        os.replace(str(tmp_path), str(DB_PATH))  # atomic swap
    finally:
        tmp_path.unlink(missing_ok=True)

    return jsonify({"status": "ok", "size_bytes": DB_PATH.stat().st_size})


# Only these paths may appear in a research zip (see push_research.py). Anything else is rejected,
# so a bad archive can't write outside RESEARCH_DIR or drop executable files there.
_RESEARCH_OK = re.compile(r"^(post\.md|claims\.md|wiki/[A-Za-z0-9][A-Za-z0-9-]*\.md|img/[a-z0-9][a-z0-9-]*\.svg)$")
_SVG_FORBIDDEN = re.compile(rb"<script|<foreignobject|javascript:|\son[a-z]+\s*=|<iframe|<embed|<object|xlink:href|href\s*=\s*[\"']https?:", re.I)
_RESEARCH_MAX_FILES, _RESEARCH_MAX_BYTES = 500, 20 * 1024 * 1024


@ingest_bp.route("/ingest/research", methods=["POST"])
def ingest_research():
    """Receive the private draft/claims/wiki bundle as a zip of markdown files and swap it in."""
    if not _token_ok(request):
        return jsonify({"error": "unauthorized"}), 401
    uploaded = request.files.get("research_zip")
    if not uploaded:
        return jsonify({"error": "missing research_zip"}), 400
    try:
        zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
    except zipfile.BadZipFile:
        return jsonify({"error": "not a zip file"}), 400

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if not infos or len(infos) > _RESEARCH_MAX_FILES or sum(i.file_size for i in infos) > _RESEARCH_MAX_BYTES:
        return jsonify({"error": "empty archive or over the size/file limit"}), 400
    bad = [i.filename for i in infos if not _RESEARCH_OK.match(i.filename)]
    if bad:
        return jsonify({"error": "disallowed paths in archive", "paths": bad[:5]}), 400

    unsafe = [i.filename for i in infos if i.filename.endswith(".svg") and _SVG_FORBIDDEN.search(zf.read(i))]
    if unsafe:
        return jsonify({"error": "svg contains script-like or external content", "paths": unsafe}), 400

    parent = RESEARCH_DIR.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="research_", dir=str(parent)))
    try:
        for i in infos:
            dest = staging / i.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(i))
        (staging / "PUSHED_AT.txt").write_text(
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), encoding="utf-8")
        if RESEARCH_DIR.exists():
            shutil.rmtree(RESEARCH_DIR)
        os.replace(str(staging), str(RESEARCH_DIR))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return jsonify({"status": "ok", "files": len(infos)})
