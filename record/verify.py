"""
record/verify.py — the independent verifier pass.

    python record/verify.py data/hyderabad            # fetch sources, locate spans, grade nodes
    python record/verify.py data/hyderabad --offline  # use cached text only, no network
    python record/verify.py data/hyderabad --report   # print status, change nothing

Rule (docs/STORY_ENGINE.md, Hyderabad brief): no node gets an evidence grade until
this pass has found the exact passage in the source text. So, per (node, source):

  1. Fetch the URL (polite: one request per source, cached under <bundle>/cache/).
     Never bypasses logins, CAPTCHAs or blocks — a 401/403/429 or a CAPTCHA page
     marks the source blocked_site and moves on.
  2. span_is_verbatim=1 → look for the span, whitespace/quote/case-normalised.
     Found → span_status='located' + offset.
     span_is_verbatim=0 (a paraphrase, e.g. from a search summary) → never 'located'.
     We print the best-matching sentence so a human can paste the verbatim passage
     into the bundle (verbatim: true) and rerun.
  3. Grade from LOCATED spans only:
       confirmed — any located primary/court source, or ≥2 located sources with
                   different independence_key among news/research/official_statement/dataset
       reported  — exactly one located credible source
       claimed   — only party_statement sources located (or layer='claim' nodes, whose
                   grade describes that the statement was MADE, not that it is true)
     reference (Wikipedia), listing and blog sources are leads only — never counted.
     Nothing located → evidence_grade stays NULL (unverified).
"""

import argparse
import hashlib
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:  # use the OS certificate store — Python's bundled CAs fail on some Windows setups and
    import truststore  # on sites that omit their intermediate cert (same fix as scrapers/pib).
    truststore.inject_into_ssl()
except ImportError:
    pass

from core.db import get_connection, init_db, sync_db  # noqa: E402

COUNTING = {"news", "research", "official_statement", "dataset"}
PRIMARY  = {"primary", "court"}
UA = "ParamaSrota-verifier/0.1 (+research; contact via repo)"


def _norm(s: str) -> str:
    s = html.unescape(s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("₹", "Rs ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"[ \t]+", " ", html.unescape(raw))


def _pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    import io
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return ""


def fetch(source: dict, cache_dir: Path, offline: bool) -> tuple[str | None, str, str]:
    """Return (text or None, access, note). Honors blocks — never retries around them."""
    cache = cache_dir / f"{source['id']}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8"), "open", "cached"
    if offline:
        return None, source.get("access") or "unchecked", "offline: not cached"
    try:
        import requests
    except ImportError:
        return None, "unchecked", "requests not installed"
    try:
        r = requests.get(source["url"], timeout=30, headers={"User-Agent": UA})
    except requests.exceptions.ProxyError as e:
        return None, "blocked_env", f"proxy/egress refused: {e.__class__.__name__}"
    except requests.exceptions.SSLError as e:  # certificate problem — a fault to report, never bypassed
        return None, "tls_error", f"SSLError: {str(e)[:120]}"
    except Exception as e:  # network down, DNS, TLS …
        return None, "blocked_env", f"{e.__class__.__name__}: {str(e)[:120]}"
    if r.status_code in (401, 407):
        return None, "login", f"HTTP {r.status_code}"
    if r.status_code in (403, 429):
        return None, "blocked_site", f"HTTP {r.status_code}"
    if r.status_code == 404:
        return None, "not_found", "HTTP 404"
    if r.status_code >= 400:
        return None, "blocked_site", f"HTTP {r.status_code}"
    ctype = r.headers.get("content-type", "")
    text = _pdf_to_text(r.content) if ("pdf" in ctype or source["url"].lower().endswith(".pdf")) else _html_to_text(r.text)
    if re.search(r"(?i)captcha|are you a robot|verify you are human", text[:5000]):
        return None, "captcha", "CAPTCHA page — not bypassed"
    if not text.strip():
        return None, "open", "fetched but no extractable text (scanned PDF?)"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text, "open", f"fetched {len(text)} chars"


def best_sentence(text: str, span: str) -> tuple[float, str]:
    """Token-overlap score of the closest sentence — a hint for humans, never a 'located'."""
    want = set(re.findall(r"\w+", _norm(span)))
    best = (0.0, "")
    for sent in re.split(r"(?<=[.!?])\s+", text):
        got = set(re.findall(r"\w+", _norm(sent)))
        if want and got:
            score = len(want & got) / len(want)
            if score > best[0]:
                best = (score, sent.strip()[:300])
    return best


def grade(located: list[dict], layer: str) -> str | None:
    if not located:
        return None
    kinds = {s["source_kind"] for s in located}
    if kinds & PRIMARY:
        g = "confirmed"
    else:
        indep = {s["independence_key"] for s in located if s["source_kind"] in COUNTING}
        g = "confirmed" if len(indep) >= 2 else "reported" if indep else None
        if g is None and "party_statement" in kinds:
            g = "claimed"
    return g


def run(bundle: Path, offline: bool, report_only: bool) -> None:
    init_db()
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache_dir = bundle / "cache"

    sources = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM rec_sources")}
    pairs = [dict(r) for r in conn.execute("""
        SELECT ns.*, n.layer FROM rec_node_sources ns JOIN rec_nodes n ON n.id = ns.node_id
        ORDER BY ns.node_id""")]
    fetched: dict[str, str | None] = {}
    stats = dict(located=0, paraphrase=0, not_found=0, unreachable=0)

    attrs = [dict(r) for r in conn.execute(
        "SELECT * FROM rec_entity_attrs WHERE source_id IS NOT NULL AND span_text IS NOT NULL")]

    needed = sorted({p["source_id"] for p in pairs} | {a["source_id"] for a in attrs})
    for sid in needed:
        src = sources[sid]
        if report_only:
            fetched[sid] = (cache_dir / f"{sid}.txt").read_text(encoding="utf-8") \
                if (cache_dir / f"{sid}.txt").exists() else None
            continue
        text, access, note = fetch(src, cache_dir, offline)
        fetched[sid] = text
        conn.execute("""UPDATE rec_sources SET access=?, access_notes=?, retrieved_at=COALESCE(?, retrieved_at),
                        local_path=COALESCE(?, local_path), content_sha256=COALESCE(?, content_sha256) WHERE id=?""",
                     (access, f"verifier {now}: {note}", now if text else None,
                      str(cache_dir / f"{sid}.txt") if text else None,
                      hashlib.sha256(text.encode()).hexdigest() if text else None, sid))
        print(f"  {access:12} {sid:32} {note}")

    def locate(source_id, span, verbatim):
        text = fetched.get(source_id)
        if text is None:
            stats["unreachable"] += 1
            return "source_unreachable", None, sources[source_id].get("access")
        if not verbatim:
            stats["paraphrase"] += 1
            score, sent = best_sentence(text, span or "")
            return "unlocated", None, f"paraphrase only; closest sentence ({score:.0%}): {sent}"
        i = _norm(text).find(_norm(span or ""))
        if i >= 0:
            stats["located"] += 1
            return "located", i, "exact (normalised) match"
        stats["not_found"] += 1
        return "not_found", None, "verbatim span not in fetched text"

    for p in pairs:
        status, off, note = locate(p["source_id"], p["span_text"], p["span_is_verbatim"])
        if not report_only:
            conn.execute("""UPDATE rec_node_sources SET span_status=?, span_offset=?, verifier_note=?, checked_at=?
                            WHERE node_id=? AND source_id=?""",
                         (status, off, note, now, p["node_id"], p["source_id"]))

    # attributes: a located span grades the attribute from its single source
    for a in attrs:
        status, _, _ = locate(a["source_id"], a["span_text"], a["span_is_verbatim"])
        g = grade([sources[a["source_id"]]], "fact") if status == "located" else None
        if not report_only:
            conn.execute("UPDATE rec_entity_attrs SET span_status=?, evidence_grade=? WHERE id=?",
                         (status, g, a["id"]))

    # grade every node from located spans only
    for (nid, layer) in conn.execute("SELECT id, layer FROM rec_nodes").fetchall():
        located = [dict(r) for r in conn.execute("""
            SELECT s.source_kind, s.independence_key FROM rec_node_sources ns
            JOIN rec_sources s ON s.id = ns.source_id
            WHERE ns.node_id=? AND ns.span_status='located'""", (nid,))]
        g = grade(located, layer)
        if not report_only:
            conn.execute("UPDATE rec_nodes SET evidence_grade=?, verified_at=? WHERE id=?",
                         (g, now if g else None, nid))

    conn.commit()
    graded = conn.execute("""SELECT COALESCE(evidence_grade,'unverified') g, COUNT(*) FROM rec_nodes GROUP BY g""").fetchall()
    conn.close()
    sync_db()
    print("spans:", stats)
    print("nodes:", {g: c for g, c in graded})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    run(a.bundle, a.offline, a.report)


if __name__ == "__main__":
    main()
