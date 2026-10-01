"""
site/build.py — Builds the static StatPlotter site (thestatplotter.com) into site/dist/.

This is the "Python/Jinja build in the repo" from DIRECTION.md decision 3. Deliberately
produces plain static files with no server-side logic, so Cloudflare Pages just serves
site/dist/ as-is — no build command needed on Cloudflare's side (the Render deploy earlier
this project taught us not to trust a remote build environment with anything it doesn't
strictly need to do).

Usage:
    python site/build.py        # renders templates -> site/dist/
"""

import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"
DIST_DIR = _HERE / "public"  # not "dist" - .gitignore has a blanket dist/ rule for Python packaging

PAGES = {
    "index.html": {},
}


def build():
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    context_defaults = {"year": date.today().year}

    for template_name, extra_context in PAGES.items():
        template = env.get_template(template_name)
        html = template.render(**context_defaults, **extra_context)
        (DIST_DIR / template_name).write_text(html, encoding="utf-8")
        print(f"  built {template_name}")

    shutil.copytree(STATIC_DIR, DIST_DIR / "static")
    print(f"  copied static/ -> {DIST_DIR.name}/static/")

    print(f"Done -> {DIST_DIR}")


if __name__ == "__main__":
    build()
