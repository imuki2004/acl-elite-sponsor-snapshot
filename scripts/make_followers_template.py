"""Create the manual-entry template for digital follower counts.

Instagram, TikTok, YouTube and X block automated collection, so follower
counts are entered BY HAND. This script pre-fills everything else: one row
per club x platform, with the official account link to open.

Which account is pre-filled (handle_source):
  club_website  - linked on the club's own homepage (most trustworthy)
  wikidata      - only found on Wikidata
  not_found     - neither source had it: search the platform, and only fill
                  it in if the account is clearly official (verified badge,
                  linked from the club website)

Output: data/raw/digital_followers_manual.csv
        -> NEVER overwritten. Delete it yourself if you want a fresh template.

Run from the project root:
    python scripts/make_followers_template.py
"""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean import CLUB_NAMES  # noqa: E402  (one list of standard names)
from parse_raw import PROFILE_URL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "digital_followers_manual.csv"

CHINA_CLUBS = {"Chengdu_Rongcheng_F.C.", "Shanghai_Port_F.C.", "Shanghai_Shenhua_F.C."}


def choose(row: pd.Series) -> pd.Series:
    website = row["website_handle"]
    wikidata = [h for h in row["wikidata_handles"].split("; ") if h]
    notes = []
    if website:
        handle, source = website, "club_website"
        if wikidata and website.lower() not in [h.lower() for h in wikidata]:
            if row["platform"] == "youtube":
                notes.append(f"Wikidata lists {wikidata[0]} - check it is the same channel")
            else:
                notes.append(f"Wikidata differs: {', '.join(wikidata)}")
    elif wikidata:
        handle, source = wikidata[0], "wikidata"
        if not row["website_downloaded"]:
            notes.append("club website blocked our download - confirm on the website")
        if len(wikidata) > 1:
            notes.append(f"other accounts on Wikidata: {', '.join(wikidata[1:])}")
    else:
        handle, source = "", "not_found"
        notes.append("search the platform; fill in only if clearly official")
    if row["club_key"] in CHINA_CLUBS:
        notes.append("mainland China club: these platforms are blocked in China, "
                     "main channels are Weibo/Douyin (not counted here)")
    return pd.Series({
        "handle": handle,
        "account_url": PROFILE_URL[row["platform"]].format(handle) if handle else "",
        "handle_source": source,
        "handle_note": "; ".join(notes),
    })


def main() -> None:
    if OUT.exists():
        print(f"{OUT.name} already exists - not overwriting your entries.")
        return
    social = pd.read_csv(ROOT / "data" / "interim" / "social_accounts_raw.csv", dtype=str).fillna("")
    social["website_downloaded"] = social["website_downloaded"] == "True"

    template = pd.concat([social[["club_key", "platform"]], social.apply(choose, axis=1)], axis=1)
    template.insert(0, "club", template["club_key"].map(CLUB_NAMES))
    # Columns YOU fill in:
    template["followers"] = ""         # as shown, e.g. 1.2M, 45.3K or 45,312
    template["date_collected"] = ""    # YYYY-MM-DD
    template["source_url"] = template["account_url"]  # change if you used another page
    template["collector_notes"] = ""

    order = {p: i for i, p in enumerate(["instagram", "tiktok", "youtube", "x"])}
    template = template.sort_values(["club", "platform"], key=lambda s: s.map(order) if s.name == "platform" else s)
    template.to_csv(OUT, index=False)

    print(f"Wrote {OUT}")
    print(template["handle_source"].value_counts().to_string())


if __name__ == "__main__":
    main()
