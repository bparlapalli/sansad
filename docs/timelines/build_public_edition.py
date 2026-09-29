"""
docs/timelines/build_public_edition.py — Regenerate the public timeline edition.

The research edition (data/timelines/*.json + timeline.html, gitignored, local
only) holds everything: facts, attributed claims, inferred events/links and
hypotheses about named people. This script writes the public edition next to
itself (docs/timelines/) with:

  - hypotheses removed
  - events with evidence 'inferred' removed, plus any link/mention pointing at them
  - links whose own evidence is 'inferred' removed
  - `reasoning` fields removed
  - EXCLUDE: events kept out by editorial decision (reason recorded below)

Usage (from the repo root):
    python docs/timelines/build_public_edition.py
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FULL = ROOT / "data" / "timelines"
FILES = ["cjp-education-minister.json", "manipur.json", "sterlite-copper.json"]

# Editorial exclusions from the public edition (kept in the research edition).
EXCLUDE = {
    "m45": "allegation against named people sourced only from a search summary, not read at source",
}


def main():
    data = {f: json.loads((FULL / f).read_text(encoding="utf-8")) for f in FILES}

    # Event ids are unique across issues (m*, s*, c*), so cross-issue refs
    # ("manipur:m33") can be matched on the bare id.
    removed = {e["id"] for d in data.values() for e in d["events"]
               if e.get("evidence") == "inferred" or e["id"] in EXCLUDE}

    def keep(ref):
        return not isinstance(ref, str) or ref.split(":")[-1] not in removed

    for f, d in data.items():
        n0 = len(d["events"])
        d["events"] = [e for e in d["events"] if e["id"] not in removed]
        for e in d["events"]:
            e.pop("reasoning", None)
            e["links"] = [l for l in e.get("links") or []
                          if l.get("evidence") != "inferred" and keep(l.get("to"))]
            if e.get("mentions"):
                e["mentions"] = [m for m in e["mentions"]
                                 if keep(m if isinstance(m, str) else m.get("id"))]
        n_hyp = len(d.get("hypotheses", []))
        d["hypotheses"] = []
        d["issue"]["edition"] = ("public: confirmed, reported and disputed facts plus attributed "
                                 "claims. Inferred events, inferred links and hypotheses are kept "
                                 "in the local research edition only.")
        (HERE / f).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{f}: events {n0} -> {len(d['events'])}, hypotheses {n_hyp} -> 0")

    # The prototype page inlines its data as one `const DATA = [...]` line.
    html = (FULL / "timeline.html").read_text(encoding="utf-8")
    m = re.search(r"^const DATA = (\[.*\]);\s*$", html, re.M)
    by_slug = {d["issue"]["slug"]: d for d in data.values()}
    new = [by_slug[o["issue"]["slug"]] for o in json.loads(m.group(1))]
    html = html[:m.start(1)] + json.dumps(new, ensure_ascii=False) + html[m.end(1):]
    (HERE / "timeline.html").write_text(html, encoding="utf-8")

    # Leak check
    text = "".join((HERE / f).read_text(encoding="utf-8") for f in FILES + ["timeline.html"])
    assert not re.search(r'"evidence":\s*"inferred"', text), "inferred item leaked"
    assert '"reasoning"' not in text, "reasoning leaked"
    assert not any(re.search(rf'"id":\s*"{i}"', text) for i in EXCLUDE), "excluded event leaked"
    print("public edition written, leak checks passed")


if __name__ == "__main__":
    main()
