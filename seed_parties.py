"""
seed_parties.py — Populate party data for members in sansad.db

Run from the sansad/ project root:
    python seed_parties.py

Uses name-matching against a known 18th Lok Sabha party roster.
"""

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
DB_PATH = _ROOT / "sansad.db"

# ── Party lookup: normalised name fragment → party abbreviation ───────────────
# Keys are lowercase substrings of the member's name (after stripping
# honorifics like Shri/Shrimati/Dr./Adv./Sushri). First match wins.

PARTY_MAP = {
    # BJP
    "gajendra singh shekhawat":   "BJP",
    "jugal kishore":              "BJP",
    "sukanta majumdar":           "BJP",
    "tejasvi surya":              "BJP",
    "naveen jindal":              "BJP",
    "rajiv pratap rudy":          "BJP",
    "p. p. chaudhary":            "BJP",
    "kota srinivasa poojary":     "BJP",
    "nishikant dubey":            "BJP",
    "ashwini vaishnaw":           "BJP",
    "jitendra singh":             "BJP",
    "basavaraj bommai":           "BJP",
    "nirmala sitharaman":         "BJP",
    "sambit patra":               "BJP",
    "rajkumar chahar":            "BJP",
    "anup sanjay dhotre":         "BJP",
    "sudheer gupta":              "BJP",
    "namdeo kirsan":              "BJP",
    "govind makthappa karjol":    "BJP",
    "alok kumar suman":           "BJP",
    "bibhu prasad tarai":         "BJP",
    "prashant yadaorao padole":   "BJP",
    "devesh shakya":              "BJP",
    "darshan singh choudhary":    "BJP",
    "eatala rajender":            "BJP",
    "sukanta kumar panigrahi":    "BJP",
    "suresh kumar shetkar":       "BJP",
    "m. mallesh babu":            "BJP",
    "bharti pardhi":              "BJP",
    "kriti devi debbarman":       "BJP",
    "d. k. aruna":                "BJP",
    "asit kumar mal":             "BJP",
    "c. m. ramesh":               "BJP",
    "shreyas m. patel":           "BJP",
    "khagen murmu":               "BJP",
    "vijay kumar dubey":          "BJP",
    "bhaskar murlidhar bhagare":  "BJP",

    # INC
    "shashi tharoor":             "INC",
    "k. c. venugopal":            "INC",
    "b. manickam tagore":         "INC",
    "benny behanan":              "INC",
    "m. k. raghavan":             "INC",
    "charanjit singh channi":     "INC",
    "manish tewari":              "INC",
    "sudhakar singh":             "INC",
    "adoor prakash":              "INC",
    "dean kuriakose":             "INC",
    "rajmohan unnithan":          "INC",
    "sasikanth senthil":          "INC",
    "angomcha bimol akoijam":     "INC",
    "vijayakumar alias vijay vasanth": "INC",
    "vijay vasanth":              "INC",
    "anto antony":                "INC",

    # TMC (All India Trinamool Congress)
    "pratima mondal":             "AITC",
    "satabdi roy banerjee":       "AITC",
    "june maliah":                "AITC",
    "kalyan banerjee":            "AITC",
    "rachna banerjee":            "AITC",
    "bapi haldar":                "AITC",
    "mahua moitra":               "AITC",
    "kakoli ghosh dastidar":      "AITC",
    "kirti azad":                 "AITC",

    # DMK
    "a. raja":                    "DMK",
    "t. sumathy":                 "DMK",
    "thamizhachi thangapandian":  "DMK",
    "kanimozhi":                  "DMK",
    "t. r. baalu":                "DMK",
    "kalanidhi veeraswamy":       "DMK",
    "malaiyarasan":               "DMK",
    "t. m. selvaganapathi":       "DMK",
    "d. m. kathir anand":         "DMK",
    "c. n. annadurai":            "DMK",
    "s. jagathratchagan":         "DMK",
    "jagathratchakan":            "DMK",
    "k. e. prakash":              "DMK",
    "tamilselvan thanga":         "DMK",
    "kumari sudha":               "DMK",
    "ganapathy rajkumar":         "DMK",

    # SP (Samajwadi Party)
    "dharmendra yadav":           "SP",
    "rajeev rai":                 "SP",
    "ananta nayak":               "SP",

    # TDP (Telugu Desam Party)
    "appalanaidu kalisetti":      "TDP",
    "g. lakshminarayana":         "TDP",
    "m. k. vishnu prasad":        "TDP",
    "balashowry vallabhaneni":    "TDP",
    "sribharat mathukumilli":     "TDP",
    "g. m. harish balayogi":      "TDP",
    "daggumalla prasada rao":     "TDP",
    "tangella uday srinivas":     "TDP",
    "chamala kiran kumar reddy":  "TDP",
    "magunta sreenivasulu reddy": "TDP",

    # YSRCP
    "byreddy shabari":            "YSRCP",
    "y. s. avinash reddy":        "YSRCP",

    # CPI(M)
    "s. venkatesan":              "CPI(M)",
    "subbarayan":                 "CPI(M)",

    # Shiv Sena (UBT)
    "anil yeshwant desai":        "Shiv Sena (UBT)",
    "arvind ganpat sawant":       "Shiv Sena (UBT)",

    # NCP (Ajit Pawar)
    "sunil dattatrey tatkare":    "NCP",
    "sanjay dina patil":          "NCP",
    "naresh ganpat mhaske":       "NCP",
    "dhairyasheel sambhajirao":   "NCP",

    # NCP (Sharad Pawar)
    "nilesh dnyandev lanke":      "NCP(SP)",

    # AIMIM
    "asaduddin owaisi":           "AIMIM",

    # IUML
    "e. t. mohammed basheer":     "IUML",

    # RSP
    "n. k. premachandran":        "RSP",

    # Kerala Congress
    "francis george":             "KC(M)",

    # MDMK
    "durai vaiko":                "MDMK",

    # SAD
    "harsimrat kaur badal":       "SAD",

    # LJP (Ram Vilas)
    "shambhavi":                  "LJP(RV)",

    # AAP
    "malvinder singh kang":       "AAP",

    # JD(S)
    "maddila gurumoorthy":        "JD(S)",

    # VCK
    "selvaraj v.":                "VCK",

    # Misc / smaller parties
    "isha khan choudhury":        "INC",
    "vishaldada prakashbapu patil": "INC",
    "raghavan":                   "INC",

    # CPI
    "g. selvam":                  "CPI",
    "k. subbarayan":              "CPI(M)",

    # Apna Dal
    "arun nehru":                 "INC",  # historical figure listed?

    # BRS (Bharat Rashtra Samithi)
    "kadiyam kavya":              "BRS",

    # BJD → BJP (joined BJP 2024)
    "bhartruhari mahtab":         "BJP",

    # BJP (Bengal)
    "saumitra khan":              "BJP",

    # INC (Tamil Nadu)
    "s. jothimani":               "INC",
}

HONORIFICS = [
    "shrimati ", "sushri ", "shri ", "dr. ", "adv. ", "prof. ",
    "col. ", "lt. ", "maj. ", "brig. ",
]

def normalize(name: str) -> str:
    n = name.lower().strip()
    for h in HONORIFICS:
        if n.startswith(h):
            n = n[len(h):]
    return n.strip()


def match_party(name: str) -> str | None:
    n = normalize(name)
    # Exact key match first
    if n in PARTY_MAP:
        return PARTY_MAP[n]
    # Substring match
    for key, party in PARTY_MAP.items():
        if key in n or n in key:
            return party
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id, name FROM members")
    rows = c.fetchall()

    updated = 0
    unmatched = []

    for member_id, name in rows:
        party = match_party(name)
        if party:
            c.execute("UPDATE members SET party = ? WHERE id = ?", (party, member_id))
            updated += 1
        else:
            unmatched.append(name)

    conn.commit()
    conn.close()

    print(f"Updated {updated}/{len(rows)} members with party data")
    if unmatched:
        print(f"\nUnmatched ({len(unmatched)}):")
        for n in sorted(unmatched):
            print(f"  {n}")


if __name__ == "__main__":
    main()
