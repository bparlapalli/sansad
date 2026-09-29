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
import re
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


def prepare_post(text: str) -> str:
    """The draft opens with an HTML comment (tag legend + 'state at draft time'). The site renders markdown with raw
    HTML disabled, so a comment would show up as visible text — and its '0 of 37 graded' is stale. Turn it into a
    readable note that points to the Claims page for the current grades."""
    m = re.match(r"\s*<!--(.*?)-->\s*", text, re.S)
    if not m:
        return text
    legend: list[str] = []
    for ln in (x.strip() for x in m.group(1).splitlines()):
        if ln.startswith(("Node ids", "State at")):
            break                                   # end of the legend; the rest is stale build info
        if ln.startswith("["):
            legend.append(ln)
        elif legend and ln:
            legend[-1] += " " + ln                  # legend entries wrap across lines in the comment
    note = ["> **How to read this draft (private, unverified).** It was written before verification, so the tags below can be "
            "out of date — **the [Claims page](/draft/claims) has the current evidence grade for every claim.**", ">"]
    note += [f"> - `{ln.split(']')[0]}]` {ln.split(']', 1)[1].strip()}" for ln in legend if "]" in ln]
    return "\n".join(note) + "\n\n" + text[m.end():]


def build_zip(bundle: Path, story: str) -> bytes:
    claims_md = bundle / "claims.md"
    env = dict(os.environ, SANSAD_DB_PATH=str(bundle / "record.db"), PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, str(_ROOT / "record" / "claims_page.py"), story, str(bundle),
                    "--out", str(claims_md)], check=True, env=env, cwd=str(_ROOT))

    # graphics are regenerated from the record DB so their grades match the claims page
    build_tl = bundle / "graphics" / "build_timeline.py"
    if build_tl.exists():
        subprocess.run([sys.executable, str(build_tl)], check=True, env=env, cwd=str(_ROOT))

    files = {"post.md": bundle / "post" / "DRAFT-v0.md", "claims.md": claims_md}
    for p in sorted((bundle / "graphics").glob("*.svg")):
        files[f"img/{p.name}"] = p
    for p in sorted((bundle / "wiki").glob("*.md")):
        files[f"wiki/{p.name}"] = p
    missing = [k for k, v in files.items() if not v.exists()]
    if missing:
        sys.exit(f"missing files: {missing}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, path in files.items():
            if arc == "post.md":   # the comment header becomes a visible, current "how to read this" note
                zf.writestr(arc, prepare_post(path.read_text(encoding="utf-8")))
            else:
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
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        wiki = sum(1 for x in z.namelist() if x.startswith("wiki/"))
    print(f"{n} files, {len(data)/1024:.0f} KB  (post, claims, {wiki} wiki pages, {n - wiki - 2} graphics)")
    if args.dry_run:
        sys.exit(0)

    site, token = os.getenv("LIVE_SITE_URL"), os.getenv("INGEST_TOKEN")
    if not site or not token:
        sys.exit("Set LIVE_SITE_URL and INGEST_TOKEN in .env first.")
    r = requests.post(site.rstrip("/") + "/ingest/research", headers={"Authorization": f"Bearer {token}"},
                      files={"research_zip": ("research.zip", data, "application/zip")}, timeout=120)
    print(f"POST /ingest/research -> {r.status_code}  {r.text.strip()}")
    r.raise_for_status()
