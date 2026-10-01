"""
scrapers/indicators/phonepe_pulse.py — PhonePe Pulse quarterly payment aggregates, all India.

Source: github.com/PhonePe/pulse (licence CDLA-Permissive-2.0). Deterministic, re-runnable,
no LLM. Files are discovered from one GitHub tree call, downloaded from
raw.githubusercontent.com (<=1 request/second), cached byte-for-byte under
data/raw/phonepe_pulse/ (gitignored) and skipped on later runs when the cached file's
git blob sha equals the tree's. Rows land in the local sansad.db only
(rec_series / rec_geo / rec_observations), each carrying source_url + source_file_sha.

CAVEAT: Pulse counts transactions processed on the PhonePe platform, not every UPI
transaction in India. Series ids keep the 'upi-' prefix per the pipeline spec.

Usage:
    python scrapers/indicators/phonepe_pulse.py --since 2018 [--state telangana] [--status] [--dry-run]
    python scrapers/indicators/phonepe_pulse.py --check --state telangana   # district-sum vs state total
"""

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    print("! truststore not installed - TLS may fail. python -m pip install --use-feature=truststore truststore")

import requests

from scrapers.indicators import store

TREE_URL = "https://api.github.com/repos/PhonePe/pulse/git/trees/master?recursive=1"
RAW_URL = "https://raw.githubusercontent.com/PhonePe/pulse/master/{path}"
USER_AGENT = ("ParamaSrota-indicators/1.0 (research; PhonePe Pulse CDLA-Permissive-2.0 fetcher; "
              "contact bharath.parlapalli@gmail.com)")
CACHE_DIR = _ROOT / "data" / "raw" / "phonepe_pulse"
MIN_INTERVAL = 1.05   # seconds between network requests
FAMILY = "phonepe_pulse"
LICENCE = "CDLA-Permissive-2.0"
SRC = "phonepe_pulse"

# PhonePe state slug (lowercase, spaces) -> ISO 3166-2:IN suffix. Unknown states are logged, never guessed.
STATE_CODES = {
    "andaman & nicobar islands": "an", "andhra pradesh": "ap", "arunachal pradesh": "ar", "assam": "as",
    "bihar": "br", "chandigarh": "ch", "chhattisgarh": "ct",
    "dadra & nagar haveli & daman & diu": "dh", "delhi": "dl", "goa": "ga", "gujarat": "gj",
    "haryana": "hr", "himachal pradesh": "hp", "jammu & kashmir": "jk", "jharkhand": "jh",
    "karnataka": "ka", "kerala": "kl", "ladakh": "ld", "lakshadweep": "ll", "madhya pradesh": "mp",
    "maharashtra": "mh", "manipur": "mn", "meghalaya": "ml", "mizoram": "mz", "nagaland": "nl",
    "odisha": "or", "puducherry": "py", "punjab": "pb", "rajasthan": "rj", "sikkim": "sk",
    "tamil nadu": "tn", "telangana": "tg", "tripura": "tr", "uttar pradesh": "up",
    "uttarakhand": "ut", "west bengal": "wb",
}
# Known district renames (raw slug -> canonical slug). Empty until a rename is verified; never guess.
DISTRICT_RENAMES: dict = {}

PINCODE_NOTE = "top-N list only (PhonePe publishes the top pincodes per state); absence != zero"

SERIES = [
    # id, name, unit, measure, geo_level, description
    ("upi-txn-count", "PhonePe transactions (count)", "count", "transactions", "state+district",
     "Quarterly count of transactions processed on PhonePe (map/transaction hover). Not all-UPI."),
    ("upi-txn-value-inr", "PhonePe transactions (value)", "INR", "transaction value", "state+district",
     "Quarterly value in INR of transactions processed on PhonePe (map/transaction hover). Not all-UPI."),
    ("upi-txn-count-pincode-top", "PhonePe transactions by pincode (count, top-N)", "count", "transactions", "pincode",
     "Top pincodes per state per quarter (top/transaction). Top-N list: absence is not zero."),
    ("upi-txn-value-inr-pincode-top", "PhonePe transactions by pincode (value, top-N)", "INR", "transaction value",
     "pincode", "Top pincodes per state per quarter (top/transaction). Top-N list: absence is not zero."),
    ("upi-registered-users", "PhonePe registered users", "count", "registered users", "state+district",
     "Registered PhonePe users at quarter end (map/user hover)."),
    ("upi-app-opens", "PhonePe app opens", "count", "app opens", "state+district",
     "PhonePe app opens in the quarter (map/user hover). Source reports 0 for early periods (not published) - "
     "omitted, not stored as zero."),
    ("upi-txn-type-count", "PhonePe transactions by type (count)", "count", "transactions", "country+state",
     "Breakdown by category (peer-to-peer, merchant, recharge...); entity_id is '<geo>#<type-slug>' "
     "(aggregated/transaction)."),
    ("upi-txn-type-value-inr", "PhonePe transactions by type (value)", "INR", "transaction value", "country+state",
     "Breakdown by category; entity_id is '<geo>#<type-slug>' (aggregated/transaction)."),
]


# ── pure parse functions (no network) ────────────────────────────────────────

def period_of(year, quarter) -> str:
    return f"{int(year)}-Q{int(quarter)}"


def slug(text: str) -> str:
    t = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def district_slug(raw: str) -> str:
    """'Hyderabad District' -> 'hyderabad'. Applies DISTRICT_RENAMES."""
    s = slug(re.sub(r"\s+district$", "", raw.strip().lower()))
    return DISTRICT_RENAMES.get(s, s)


def parse_map_txn(j: dict) -> list:
    """map/transaction/hover -> [(raw name, count, amount)] (TOTAL metric)."""
    out = []
    for item in (j.get("data") or {}).get("hoverDataList") or []:
        for m in item.get("metric") or []:
            if m.get("type") == "TOTAL":
                out.append((item["name"], m["count"], m["amount"]))
    return out


def parse_map_user(j: dict) -> list:
    """map/user/hover -> [(raw name, registeredUsers, appOpens)]."""
    hd = (j.get("data") or {}).get("hoverData") or {}
    return [(n, v.get("registeredUsers"), v.get("appOpens")) for n, v in hd.items()]


def parse_top_pincodes(j: dict) -> list:
    out = []
    for item in (j.get("data") or {}).get("pincodes") or []:
        m = item.get("metric") or {}
        out.append((str(item["entityName"]), m.get("count"), m.get("amount")))
    return out


def parse_agg_txn(j: dict) -> list:
    """aggregated/transaction -> [(category name, count, amount)] (TOTAL instrument)."""
    out = []
    for cat in (j.get("data") or {}).get("transactionData") or []:
        for pi in cat.get("paymentInstruments") or []:
            if pi.get("type") == "TOTAL":
                out.append((cat["name"], pi["count"], pi["amount"]))
    return out


# ── discovery + cache ────────────────────────────────────────────────────────

class Fetcher:
    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers["User-Agent"] = USER_AGENT
        self._last = 0.0
        self.requests_made = 0

    def _wait(self):
        d = MIN_INTERVAL - (time.time() - self._last)
        if d > 0:
            time.sleep(d)
        self._last = time.time()
        self.requests_made += 1

    def get(self, url, retries=4):
        for attempt in range(retries):
            self._wait()
            try:
                r = self.sess.get(url, timeout=60)
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code}", response=r)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise
                wait = 5 * 2 ** attempt
                print(f"    retry in {wait}s ({e.__class__.__name__}: {e})")
                time.sleep(wait)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


PATH_RE = re.compile(
    r"^data/(?P<kind>map/transaction/hover|map/user/hover|top/transaction|aggregated/transaction)"
    r"/country/india/(?:state/(?P<state>[^/]+)/)?(?P<year>\d{4})/(?P<q>[1-4])\.json$")


def select_files(tree: list, since: int, state) -> list:
    files = []
    for t in tree:
        m = PATH_RE.match(t["path"])
        if not m:
            continue
        kind, st, yr, q = m["kind"], m["state"], int(m["year"]), int(m["q"])
        if yr < since:
            continue
        if st is None and kind == "top/transaction":
            continue          # country-level top list: not needed (state totals come from map/hover)
        if state and st and st != state:
            continue
        files.append({"path": t["path"], "sha": t["sha"], "kind": kind, "state": st, "year": yr, "q": q})
    files.sort(key=lambda f: (f["year"], f["q"], f["kind"], f["state"] or ""))
    return files


def load_tree(fetcher) -> list:
    cache = CACHE_DIR / "_tree.json"
    try:
        j = fetcher.get(TREE_URL).json()
        if j.get("truncated"):
            raise RuntimeError("GitHub tree truncated - switch to per-directory listing")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(j), encoding="utf-8")
        return j["tree"]
    except requests.RequestException as e:
        if not cache.exists():
            raise
        print(f"! tree fetch failed ({e}); using cached tree")
        return json.loads(cache.read_text(encoding="utf-8"))["tree"]


def ensure_cached(fetcher, f, dry_run):
    """Return (bytes, downloaded_now). In dry-run, missing files return (None, False)."""
    local = CACHE_DIR / f["path"]
    if local.exists():
        data = local.read_bytes()
        if git_blob_sha(data) == f["sha"]:
            return data, False
    if dry_run:
        return None, False
    data = fetcher.get(RAW_URL.format(path=f["path"])).content
    got = git_blob_sha(data)
    if got != f["sha"]:
        print(f"    ! sha mismatch for {f['path']} (tree {f['sha'][:8]} vs got {got[:8]}) - using the downloaded sha")
        f["sha"] = got
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    return data, True


# ── loading into the DB ──────────────────────────────────────────────────────

class Ctx:
    def __init__(self, conn):
        self.conn = conn
        self.counts = defaultdict(Counter)      # series -> {new, changed, same}
        self.unmapped = Counter()               # (kind, raw name) -> occurrences
        self.raw_names = defaultdict(set)       # geo id -> raw names seen
        self.periods_by_geo = defaultdict(set)

    def obs(self, series, entity, period, value, url, sha, note=None):
        if value is None:
            return
        res = store.upsert_observation(self.conn, series, entity, period, float(value), url, sha, note)
        self.counts[series][res] += 1


def state_geo(ctx, state_name: str):
    code = STATE_CODES.get(state_name.strip().lower())
    if not code:
        ctx.unmapped[("state", state_name)] += 1
        return None
    gid = f"in-{code}"
    store.ensure_geo(ctx.conn, "in", "country", "India", None, SRC)
    store.ensure_geo(ctx.conn, gid, "state", state_name, "in", SRC)
    ctx.raw_names[gid].add(state_name)
    return gid


def geo_for(ctx, st, st_name, raw):
    """Geo id for a hover row: a state (country file) or a district (state file)."""
    if st is None:
        return state_geo(ctx, raw)
    parent = state_geo(ctx, st_name)
    ds = district_slug(raw)
    if not parent or not ds:
        ctx.unmapped[("district", f"{st_name}/{raw}")] += 1
        return None
    gid = f"{parent}-{ds}"
    store.ensure_geo(ctx.conn, gid, "district", raw, parent, SRC)
    ctx.raw_names[gid].add(raw)
    return gid


def load_file(ctx: Ctx, f: dict, data: bytes):
    j = json.loads(data)
    url = RAW_URL.format(path=f["path"])
    sha = f["sha"]
    period = period_of(f["year"], f["q"])
    kind, st = f["kind"], f["state"]
    st_name = st.replace("-", " ") if st else None

    if kind == "map/transaction/hover":
        for raw, cnt, amt in parse_map_txn(j):
            gid = geo_for(ctx, st, st_name, raw)
            if not gid:
                continue
            ctx.periods_by_geo[gid].add(period)
            ctx.obs("upi-txn-count", gid, period, cnt, url, sha)
            ctx.obs("upi-txn-value-inr", gid, period, amt, url, sha)

    elif kind == "map/user/hover":
        for raw, users, opens in parse_map_user(j):
            gid = geo_for(ctx, st, st_name, raw)
            if not gid:
                continue
            ctx.obs("upi-registered-users", gid, period, users, url, sha)
            if opens:                            # 0 = not published, not a real zero
                ctx.obs("upi-app-opens", gid, period, opens, url, sha)

    elif kind == "top/transaction":
        parent = state_geo(ctx, st_name)
        if not parent:
            return
        for pin, cnt, amt in parse_top_pincodes(j):
            gid = f"pin-{pin}"
            store.ensure_geo(ctx.conn, gid, "pincode", pin, parent, SRC)
            ctx.obs("upi-txn-count-pincode-top", gid, period, cnt, url, sha, PINCODE_NOTE)
            ctx.obs("upi-txn-value-inr-pincode-top", gid, period, amt, url, sha, PINCODE_NOTE)

    elif kind == "aggregated/transaction":
        if st is None:
            gid = "in"
            store.ensure_geo(ctx.conn, "in", "country", "India", None, SRC)
        else:
            gid = state_geo(ctx, st_name)
            if not gid:
                return
        for cat, cnt, amt in parse_agg_txn(j):
            ent = f"{gid}#{slug(cat)}"
            ctx.obs("upi-txn-type-count", ent, period, cnt, url, sha)
            ctx.obs("upi-txn-type-value-inr", ent, period, amt, url, sha)


def register_series(conn):
    for sid, name, unit, measure, lvl, desc in SERIES:
        store.ensure_series(conn, sid, name, unit, measure, lvl, "quarterly", FAMILY, LICENCE, desc)


# ── commands ─────────────────────────────────────────────────────────────────

def run(since: int, state, dry_run: bool):
    fetcher = Fetcher()
    tree = load_tree(fetcher)
    files = select_files(tree, since, state)
    print(f"{len(files)} source files in scope (since {since}" + (f", state={state}" if state else "") + ")")
    conn = None if dry_run else store.open_db()
    ctx = None
    if conn:
        register_series(conn)
        ctx = Ctx(conn)
    missing = downloaded = 0
    t0 = time.time()
    for i, f in enumerate(files, 1):
        data, dl = ensure_cached(fetcher, f, dry_run)
        if data is None:
            missing += 1
            continue
        downloaded += dl
        if ctx:
            load_file(ctx, f, data)
            if i % 100 == 0:
                conn.commit()
        if dl and downloaded % 100 == 0:
            print(f"  ... {i}/{len(files)} files, {downloaded} downloaded, {time.time()-t0:.0f}s", flush=True)
    if dry_run:
        print(f"dry-run: {missing} files would be downloaded (~{missing*MIN_INTERVAL/60:.0f} min at 1 req/s), "
              f"{len(files)-missing} already cached; nothing written")
        return
    conn.commit()
    print(f"downloaded {downloaded} files in {time.time()-t0:.0f}s")
    print(f"{'rows written':32s} {'new':>7} {'changed':>7} {'same':>7}")
    for s, c in sorted(ctx.counts.items()):
        print(f"  {s:30s} {c['new']:>7} {c['changed']:>7} {c['same']:>7}")
    report_naming(ctx)
    conn.close()


def report_naming(ctx: Ctx):
    if ctx.unmapped:
        print("UNMAPPED names (skipped, not guessed):")
        for (k, n), c in sorted(ctx.unmapped.items()):
            print(f"  {k}: {n!r} x{c}")
    else:
        print("unmapped names: none")
    multi = {g: sorted(n) for g, n in ctx.raw_names.items() if len(n) > 1}
    if multi:
        print("geo ids reached by more than one raw spelling:")
        for g, n in sorted(multi.items()):
            print(f"  {g}: {n}")
    all_periods = sorted({p for s in ctx.periods_by_geo.values() for p in s})
    if all_periods:
        last = all_periods[-1]
        gone = sorted(g for g, s in ctx.periods_by_geo.items() if last not in s)
        if gone:
            print(f"geos present earlier but absent in {last} ({len(gone)}): {', '.join(gone[:60])}")


def status():
    conn = store.open_db()
    print(f"{'series':32s} {'rows':>8} {'entities':>9} {'first':>8} {'latest':>8}  last fetch")
    for (sid,) in conn.execute("SELECT id FROM rec_series WHERE source_family=? ORDER BY id", (FAMILY,)).fetchall():
        n, e, a, b, r = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT entity_id), MIN(period), MAX(period), MAX(retrieved_at) "
            "FROM rec_observations WHERE series_id=?", (sid,)).fetchone()
        print(f"{sid:32s} {n:>8} {e:>9} {a or '-':>8} {b or '-':>8}  {r or '-'}")
    print("geo:", dict(conn.execute("SELECT level, COUNT(*) FROM rec_geo WHERE source=? GROUP BY level", (SRC,)).fetchall()))
    n = sum(1 for _ in CACHE_DIR.rglob("*.json")) if CACHE_DIR.exists() else 0
    print(f"raw cache: {CACHE_DIR} ({n} files)")


def check(state: str, series="upi-txn-count") -> bool:
    """District rows should sum to within 1% of the state total, per quarter."""
    conn = store.open_db()
    sid = f"in-{STATE_CODES[state.replace('-', ' ')]}"
    print(f"check {state}: sum of districts vs state total ({series})")
    worst = 0.0
    for period, tot in conn.execute(
            "SELECT period, value FROM rec_observations WHERE series_id=? AND entity_id=? ORDER BY period",
            (series, sid)).fetchall():
        s, n = conn.execute(
            "SELECT SUM(o.value), COUNT(*) FROM rec_observations o JOIN rec_geo g ON g.id=o.entity_id "
            "WHERE o.series_id=? AND o.period=? AND g.level='district' AND g.parent_id=?",
            (series, period, sid)).fetchone()
        if not n:
            continue
        diff = (s - tot) / tot * 100
        worst = max(worst, abs(diff))
        print(f"  {period}: districts={s:,.0f} ({n}) state={tot:,.0f} diff={diff:+.3f}% {'OK' if abs(diff) <= 1 else 'FAIL'}")
    print(f"max abs diff {worst:.3f}%")
    return worst <= 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", type=int, default=2018)
    ap.add_argument("--state", help="PhonePe state slug, e.g. telangana, tamil-nadu")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="plan only: no downloads, no DB writes")
    ap.add_argument("--check", action="store_true", help="district-sum vs state-total check (needs --state)")
    a = ap.parse_args()
    if a.status:
        return status()
    if a.check:
        if not a.state:
            ap.error("--check needs --state")
        sys.exit(0 if check(a.state) else 1)
    run(a.since, a.state, a.dry_run)


if __name__ == "__main__":
    main()
