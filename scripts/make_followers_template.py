"""Create the manual-entry template for digital follower counts.

Instagram, TikTok, YouTube and X block automated collection, so follower
counts are entered BY HAND. This script pre-fills everything else: one row
per club x platform, with the official account link to open.

Which account is pre-filled (handle_source), best evidence first:
  club_website       - linked on the club's own homepage
  wikidata           - recorded on Wikidata (club website not available)
  research_confirmed - found by research, strong evidence (e.g. YouTube
                       verified badge); see data/reference/social_handles_research.csv
  research_check     - found by research, likely but NOT confirmed -> check it
  not_found          - nothing found: search the platform, fill in only if
                       clearly official (verified badge / linked from club site)

Platforms:
  instagram, tiktok, youtube, x  -> all 24 clubs; counts_in_core_total = yes
  weibo, douyin                  -> mainland-China clubs only, where the core
                                    platforms are blocked; counts_in_core_total = no
                                    (reported separately so clubs stay comparable)

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
from parse_raw import CORE_PLATFORMS, PROFILE_URL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "digital_followers_manual.csv"

CHINA_CLUBS = {  # club_key -> Chinese club name, to search on Weibo/Douyin
    "Chengdu_Rongcheng_F.C.": "成都蓉城足球俱乐部",
    "Shanghai_Port_F.C.": "上海海港足球俱乐部",
    "Shanghai_Shenhua_F.C.": "上海申花足球俱乐部",
}
CHINA_PLATFORMS = ["weibo", "douyin"]
PLATFORM_ORDER = CORE_PLATFORMS + CHINA_PLATFORMS


def youtube_same_channel() -> set:
    """Clubs whose website YouTube link and Wikidata channel id resolve to the
    same channel (checked by scripts/lookup_youtube_channels.py)."""
    path = ROOT / "data" / "raw" / "youtube_channel_lookup.csv"
    if not path.exists():
        return set()
    lookup = pd.read_csv(path, dtype=str).fillna("")
    resolved = lookup[lookup["lookup"] == "resolve"]
    ids = resolved.groupby("club_key")["channel_id"].nunique()
    sources = resolved.groupby("club_key")["found_via"].nunique()
    return set(ids[(ids == 1) & (sources == 2)].index)


def choose(row: pd.Series, research: pd.DataFrame, same_channel: set) -> pd.Series:
    website = row["website_handle"]
    wikidata = [h for h in row["wikidata_handles"].split("; ") if h]
    key = (row["club_key"], row["platform"])
    notes = []
    if website:
        handle, source = website, "club_website"
        if wikidata and website.lower() not in [h.lower() for h in wikidata]:
            if row["platform"] == "youtube" and row["club_key"] in same_channel:
                pass  # different link formats, but verified to be the same channel
            else:
                notes.append(f"Wikidata differs: {', '.join(wikidata)}")
    elif wikidata:
        handle, source = wikidata[0], "wikidata"
        if not row["website_downloaded"] and row["platform"] in CORE_PLATFORMS:
            notes.append("club website blocked our download - confirm on the website")
        if len(wikidata) > 1:
            notes.append(f"other accounts on Wikidata: {', '.join(wikidata[1:])}")
    elif key in research.index:
        found = research.loc[key]
        handle, source = found["handle"], f"research_{found['confidence']}"
        notes.append(found["evidence"])
    else:
        handle, source = "", "not_found"
        notes.append("search the platform; fill in only if clearly official")

    if row["club_key"] in CHINA_CLUBS and row["platform"] in CORE_PLATFORMS:
        notes.append("mainland China club: platform blocked in China, account may not exist")
    if row["platform"] in CHINA_PLATFORMS and not handle:
        notes.append(f"search '{CHINA_CLUBS[row['club_key']]}' and use the verified (blue V) account")
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

    # Core platforms for every club; Weibo + Douyin only for the China clubs
    china = social["club_key"].isin(CHINA_CLUBS)
    social = social[social["platform"].isin(CORE_PLATFORMS) | (china & (social["platform"] == "weibo"))]
    douyin = pd.DataFrame({"club_key": list(CHINA_CLUBS), "platform": "douyin"})
    social = pd.concat([social, douyin], ignore_index=True).fillna("")

    research = pd.read_csv(ROOT / "data" / "reference" / "social_handles_research.csv",
                           dtype=str).set_index(["club_key", "platform"])
    same_channel = youtube_same_channel()

    template = pd.concat([
        social[["club_key", "platform"]],
        social.apply(choose, axis=1, research=research, same_channel=same_channel),
    ], axis=1)
    template.insert(0, "club", template["club_key"].map(CLUB_NAMES))
    template.insert(3, "counts_in_core_total",
                    template["platform"].isin(CORE_PLATFORMS).map({True: "yes", False: "no"}))
    # Columns YOU fill in:
    template["followers"] = ""         # as shown, e.g. 1.2M, 45.3K, 45,312 or 12万
    template["date_collected"] = ""    # YYYY-MM-DD
    template["source_url"] = template["account_url"]  # change if you used another page
    template["collector_notes"] = ""

    template["_order"] = template["platform"].map(PLATFORM_ORDER.index)
    template = template.sort_values(["club", "_order"]).drop(columns="_order")
    template.to_csv(OUT, index=False)

    print(f"Wrote {OUT} ({len(template)} rows)")
    print(template["handle_source"].value_counts().to_string())


if __name__ == "__main__":
    main()
