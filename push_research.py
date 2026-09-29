"""
push_research.py — Send the private Hyderabad draft + claims + wiki to the live site's /draft section.

Builds a zip of markdown files from the (private) research folder and POSTs it to /ingest/research
with the same INGEST_TOKEN as push_public_db.py. Nothing here goes to GitHub; the zip is built in
memory and the live site keeps it only in its own ephemeral folder (wiped by a redeploy → re-run this).

    python push_research.py                       # uses data/research/hyderabad
    python push_research.py --bundle path/to/bundle
    python push_research.py --dry-run             # list what would be sent

Needs, in .env or the environment:  LIVE_SITE_URL, INGEST_TOKEN
The claims page is regenerated first from the local record DB (record.db), so it is always current.
"""
import argparse
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import requests

_ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip()


_load_env_file(_ROOT / ".env")


def build_zip(bundle: Path, story: str) -> bytes:
    claims_md = bundle / "claims.md"
    env = dict(os.environ, SANSAD_DB_PATH=str(bundle / "record.db"), PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, str(_ROOT / "record" / "claims_page.py"), story, str(bundle),
                    "--out", str(claims_md)], check=True, env=env, cwd=str(_ROOT))

    files = {"post.md": bundle / "post" / "DRAFT-v0.md", "claims.md": claims_md}
    for p in sorted((bundle / "wiki").glob("*.md")):
        files[f"wiki/{p.name}"] = p
    missing = [k for k, v in files.items() if not v.exists()]
    if missing:
        sys.exit(f"missing files: {missing}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, path in files.items():
            zf.write(path, arc)
    return buf.getvalue()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=str(_ROOT / "data" / "research" / "hyderabad"))
    ap.add_argument("--story", default="hyd-post-1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = build_zip(Path(args.bundle), args.story)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        n = len(z.namelist())
    print(f"{n} files, {len(data)/1024:.0f} KB  (post.md, claims.md, {n-2} wiki pages)")
    if args.dry_run:
        sys.exit(0)

    site, token = os.getenv("LIVE_SITE_URL"), os.getenv("INGEST_TOKEN")
    if not site or not token:
        sys.exit("Set LIVE_SITE_URL and INGEST_TOKEN in .env first.")
    r = requests.post(site.rstrip("/") + "/ingest/research", headers={"Authorization": f"Bearer {token}"},
                      files={"research_zip": ("research.zip", data, "application/zip")}, timeout=120)
    print(f"POST /ingest/research -> {r.status_code}  {r.text.strip()}")
    r.raise_for_status()
