"""
record/review_form.py — build a Google Form for non-technical reviewers.

    python record/review_form.py hyd-post-1 out/ReviewForm.gs

Writes a Google Apps Script. Paste it into script.google.com and press Run once:
it creates a Google Form (one claim per page, big multiple-choice answers, optional
notes) plus a linked response Sheet, and logs both links. No developer setup needed.

Every question title carries "(ref: <node_id>)" so record/import_reviews.py can map
the Form's CSV export back to rec_reviews.

The generated script contains the story's (private, unverified) claims — write it into
the private research repo, never into this public one.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection  # noqa: E402

SECTION_ORDER = {"boomed": 0, "risk": 1, "next": 2, "who": 3}
SECTION_TITLE = {"boomed": "Why some areas boomed", "risk": "What could stall growth",
                 "next": "Where growth may go next", "who": "Who said what"}
LEADS_ONLY = {"reference", "listing", "blog"}

CHOICES = ["✅ Yes, the source says this",
           "❌ No, it says something different",
           "🤷 Can't tell / the link didn't open"]
CLAIM_CHOICES = ["✅ Yes, the source shows they said this",
                 "❌ No, they said something different",
                 "🤷 Can't tell / the link didn't open"]


def human_date(d: str | None, precision: str) -> str:
    if not d:
        return "Date not known"
    try:
        if precision == "year" or len(d) == 4:
            return d[:4]
        if precision == "month" or len(d) == 7:
            return date.fromisoformat(d[:7] + "-01").strftime("%b %Y")
        dt = date.fromisoformat(d[:10])   # "%-d" isn't supported by Windows' strftime → build the day by hand
        return f"{dt.day} {dt.strftime('%b %Y')}" + (" (approx.)" if precision == "approx" else "")
    except ValueError:
        return d


def claims(conn, story: str) -> list[dict]:
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM rec_entities")}
    rows = conn.execute("""
        SELECT n.*, sn.section FROM rec_nodes n JOIN rec_story_nodes sn ON sn.node_id = n.id
        WHERE sn.story_id = ?""", (story,)).fetchall()
    out = []
    for n in sorted(rows, key=lambda r: (SECTION_ORDER.get(r["section"], 9), r["date"] or "9999")):
        srcs = conn.execute("""
            SELECT s.url, s.publisher, s.source_kind FROM rec_node_sources ns
            JOIN rec_sources s ON s.id = ns.source_id WHERE ns.node_id = ?""", (n["id"],)).fetchall()
        srcs = sorted(srcs, key=lambda s: s["source_kind"] in LEADS_ONLY)
        actor = names.get(n["actor_id"], n["actor_id"] or "")
        if n["layer"] == "claim" and n["action"].startswith('"'):
            text = f"{actor} said: {n['action']}"
        else:
            text = f"{actor} {n['action']}."
        if n["layer"] == "claim":
            text += ("\n\n(This is what someone SAID. Please check that they said it — "
                     "not whether it is true.)")
        out.append(dict(
            id=n["id"], section=SECTION_TITLE.get(n["section"], n["section"] or ""),
            when=human_date(n["date"], n["date_precision"]), text=text,
            is_claim=n["layer"] == "claim",
            sources=[dict(url=s["url"], name=s["publisher"] + (" (background only)" if s["source_kind"] in LEADS_ONLY else ""))
                     for s in srcs]))
    return out


TEMPLATE = r"""/**
 * ParamaSrota — claim review form builder (generated __TODAY__ by record/review_form.py)
 *
 * HOW TO USE (one time, ~3 minutes):
 *   1. Go to https://script.google.com  →  New project.
 *   2. Delete everything in the editor, paste this whole file, press Save.
 *   3. Choose the function "buildForm" at the top and press Run.
 *      Google asks for permission (Forms + Sheets in YOUR Drive) → Allow.
 *   4. Open "Execution log": it prints the link to SEND (reviewer link)
 *      and the link to EDIT. Responses collect in a Sheet in your Drive.
 *
 * PRIVATE: contains unverified draft claims. Share the reviewer link only with reviewers.
 */
var TITLE = __TITLE__;
var CLAIMS = __CLAIMS__;
var CHOICES = __CHOICES__;
var CLAIM_CHOICES = __CLAIM_CHOICES__;

function buildForm() {
  var form = FormApp.create(TITLE);
  form.setDescription(
    "Thank you for helping check our facts!\n\n" +
    "You will see one statement per page (" + CLAIMS.length + " in total).\n" +
    "For each one:\n" +
    "  1. Tap the source link to open it.\n" +
    "  2. Read it, then choose Yes, No, or Can't tell.\n" +
    "  3. If you like, write a note: what the source actually says, or anything you know.\n\n" +
    "Nothing is required. You can skip any statement. Press Next to move on.");
  form.setProgressBar(true);
  form.setAllowResponseEdits(true);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage("Thank you! Your answers are saved. You can use the link again any time to review more.");

  form.addTextItem().setTitle("Your name").setRequired(true);

  var lastSection = "";
  for (var i = 0; i < CLAIMS.length; i++) {
    var c = CLAIMS[i];
    var n = i + 1;
    var ref = " (ref: " + c.id + ")";
    var links = c.sources.map(function (s) { return "• " + s.name + ": " + s.url; }).join("\n");
    var header = (c.section !== lastSection ? c.section.toUpperCase() + "\n\n" : "");
    lastSection = c.section;
    form.addPageBreakItem()
      .setTitle("Statement " + n + " of " + CLAIMS.length)
      .setHelpText(header + c.when + "\n\n" + c.text + "\n\nSources to check:\n" + (links || "(none yet)"));
    form.addMultipleChoiceItem()
      .setTitle("Statement " + n + ": does the source say this?" + ref)
      .setChoiceValues(c.is_claim ? CLAIM_CHOICES : CHOICES)
      .setRequired(false);
    form.addParagraphTextItem()
      .setTitle("Statement " + n + ": notes (optional)" + ref)
      .setHelpText("What does the source actually say? Or: what do you know that is different?")
      .setRequired(false);
    form.addTextItem()
      .setTitle("Statement " + n + ": another link (optional)" + ref)
      .setHelpText("If you know a different source (news story, government order), paste its link here.")
      .setRequired(false);
  }

  var sheet = SpreadsheetApp.create(TITLE + " (responses)");
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log("SEND THIS LINK to reviewers: " + form.getPublishedUrl());
  Logger.log("Edit the form:              " + form.getEditUrl());
  Logger.log("Responses sheet:            " + sheet.getUrl());
}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story")
    ap.add_argument("out", type=Path)
    ap.add_argument("--title", default="ParamaSrota fact check — Hyderabad")
    a = ap.parse_args()

    conn = get_connection()
    cs = claims(conn, a.story)
    conn.close()
    js = (TEMPLATE.replace("__TODAY__", date.today().isoformat())
                  .replace("__TITLE__", json.dumps(a.title, ensure_ascii=False))
                  .replace("__CLAIMS__", json.dumps(cs, ensure_ascii=False, indent=1))
                  .replace("__CHOICES__", json.dumps(CHOICES, ensure_ascii=False))
                  .replace("__CLAIM_CHOICES__", json.dumps(CLAIM_CHOICES, ensure_ascii=False)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(js, encoding="utf-8")
    print(f"✓ {len(cs)} claims → {a.out}")


if __name__ == "__main__":
    main()
