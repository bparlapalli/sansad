"""
app/ingest_bp.py — Receives the trimmed public.db pushed from the local
machine and swaps it in atomically. Machine-to-machine only: a bearer token
(INGEST_TOKEN env var), not the admin session login.

The full dataset never reaches this server — only whatever
parser/export_public_db.py chose to include (see push_public_db.py).
"""

import os
import sqlite3
import tempfile
from pathlib import Path

from flask import Blueprint, request, jsonify

from core.db import DB_PATH

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
