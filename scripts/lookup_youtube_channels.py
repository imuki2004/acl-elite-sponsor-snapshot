"""Look up YouTube channels: resolve known links and search for missing ones.

YouTube (unlike Instagram/TikTok/X) serves its pages without a login, so we
can check two things automatically:
  1. RESOLVE: every YouTube link we already have (from club websites and
     Wikidata) -> channel id, channel name, verified badge. This tells us if a
     website link like 'user/FCMZ1989' and a Wikidata channel id are the same
     channel.
  2. SEARCH: for clubs with no YouTube link, YouTube's own channel search.
     A 'verified' badge is strong evidence the channel is the official one.

Only evidence is recorded here. Which account to use is decided by hand in
data/reference/social_handles_research.csv (with the reason).

Output: data/raw/youtube_channel_lookup.csv (one row per resolved link or
search result, with fetched_at_utc). Re-running overwrites it.

Run from the project root:
    python scripts/lookup_youtube_channels.py
"""

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "youtube_channel_lookup.csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Search terms for clubs where neither the website nor Wikidata had a channel
SEARCHES = {
    "Al-Ahli_Saudi_FC": "Al Ahli Saudi Club",
    "Al-Ittihad_Club_(Jeddah)": "Ittihad Club",
    "Al_Sadd_SC": "Al Sadd SC",
    "Al_Wahda_FC": "Al Wahda FC",
    "Sharjah_FC": "Sharjah FC",
    "Johor_Darul_Ta'zim_F.C.": "JDT Johor Darul Tazim",  # apostrophe query returned nothing
    "FC_Nasaf": "FC Nasaf",
    "Shanghai_Port_F.C.": "Shanghai Port FC",
    "Shanghai_Shenhua_F.C.": "Shanghai Shenhua",
    "Chengdu_Rongcheng_F.C.": "Chengdu Rongcheng",
    "Sanfrecce_Hiroshima": "Sanfrecce Hiroshima",
}


def get(url: str) -> str:
    request = Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def initial_data(html: str) -> dict:
    match = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
    return json.loads(match.group(1)) if match else {}


def find_all(obj, key):
    """Yield every value stored under `key` anywhere in a nested JSON object."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from find_all(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from find_all(v, key)


def resolve(url: str) -> dict:
    """Open a channel page and read its id, name and handle.

    The verified badge is not reliably present in the channel page data, so
    it is recorded as 'unknown' here; search results do show it reliably."""
    data = initial_data(get(url))
    meta = next(find_all(data, "channelMetadataRenderer"), {})
    return {
        "channel_id": meta.get("externalId", ""),
        "channel_title": meta.get("title", ""),
        "channel_handle": meta.get("vanityChannelUrl", "").rsplit("/", 1)[-1],
        "verified": "unknown",
    }


def search(query: str, top: int = 4) -> list[dict]:
    url = "https://www.youtube.com/results?" + urlencode({"search_query": query, "sp": "EgIQAg=="})
    results = []
    for channel in list(find_all(initial_data(get(url)), "channelRenderer"))[:top]:
        badges = json.dumps(channel.get("ownerBadges", []))
        results.append({
            "channel_id": channel["channelId"],
            "channel_title": channel["title"]["simpleText"],
            "channel_handle": channel.get("navigationEndpoint", {}).get("browseEndpoint", {})
                                     .get("canonicalBaseUrl", "").lstrip("/"),
            "verified": "VERIFIED" in badges,
            "lookup_url": url,
        })
    return results


def main() -> None:
    now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    social = pd.read_csv(ROOT / "data" / "interim" / "social_accounts_raw.csv", dtype=str).fillna("")
    youtube = social[social["platform"] == "youtube"]
    rows = []

    # 1. Resolve every link we already have
    for _, r in youtube.iterrows():
        links = [("club_website", r["website_handle"])] + [
            ("wikidata", h) for h in r["wikidata_handles"].split("; ") if h]
        for source, handle in links:
            if not handle:
                continue
            url = f"https://www.youtube.com/{handle}"
            try:
                info = resolve(url)
            except Exception as error:
                info = {"channel_title": f"ERROR: {error}"}
            rows.append({"club_key": r["club_key"], "lookup": "resolve", "found_via": source,
                         "query_or_link": handle, "lookup_url": url, "rank": "",
                         "fetched_at_utc": now(), **info})
            print(f"resolve {r['club_key']:<28} {handle:<40} -> {info.get('channel_id', '')}")
            time.sleep(1)

    # 2. Search for clubs without a channel
    for club_key, query in SEARCHES.items():
        for rank, result in enumerate(search(query), start=1):
            rows.append({"club_key": club_key, "lookup": "search", "found_via": "youtube_search",
                         "query_or_link": query, "rank": rank, "fetched_at_utc": now(), **result})
        print(f"search  {club_key:<28} '{query}' done")
        time.sleep(1)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
