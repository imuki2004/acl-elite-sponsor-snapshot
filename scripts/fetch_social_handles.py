"""Download each club's official social-media accounts from Wikidata.

Why Wikidata: social platforms (Instagram, TikTok, X) block automated access,
so follower COUNTS must be collected by hand. But the account HANDLES are
recorded on Wikidata, which lets us pre-fill the template with the right
official accounts instead of guessing them.

Steps:
  1. Wikipedia API: club article (our club_key) -> Wikidata item id (Q-number)
  2. Wikidata API:  item id -> claims, incl. social-media properties
Both raw JSON responses are saved untouched in data/raw/ and logged in
data/raw/fetch_log.csv, like every other download.

Run from the project root (skips if the files already exist):
    python scripts/fetch_social_handles.py
"""

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import csv
import hashlib

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
HEADERS = {"User-Agent": "acl-sponsor-snapshot-research/1.0 (data project)"}


def fetch(url: str, filename: str) -> bytes:
    """Download url to data/raw/filename (unless it exists) and log it."""
    out = RAW / filename
    if out.exists():
        print(f"skip   {filename} (already exists)")
        return out.read_bytes()
    with urlopen(Request(url, headers=HEADERS), timeout=30) as response:
        body, status = response.read(), response.status
    out.write_bytes(body)
    with open(RAW / "fetch_log.csv", "a", newline="") as log:
        csv.writer(log).writerow([
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), filename, status,
            len(body), hashlib.sha256(body).hexdigest(), url])
    print(f"{status}  {filename} ({len(body)} bytes)")
    return body


def main() -> None:
    clubs = pd.read_csv(ROOT / "data" / "interim" / "clubs_raw.csv", dtype=str)
    titles = "|".join(clubs["club_key"].str.replace("_", " "))

    # 1. Wikipedia article -> Wikidata item id (follows redirects)
    fetch("https://en.wikipedia.org/w/api.php?" + urlencode({
        "action": "query", "format": "json", "prop": "pageprops",
        "ppprop": "wikibase_item", "redirects": 1, "titles": titles,
    }), "wikidata_club_ids.json")

    ids = pd.read_json(RAW / "wikidata_club_ids.json", typ="series")["query"]["pages"]
    qids = sorted(p["pageprops"]["wikibase_item"] for p in ids.values() if "pageprops" in p)
    print(f"  found {len(qids)} Wikidata items for {len(clubs)} clubs")

    # 2. Wikidata item -> claims (social-media properties are read in parse_raw.py)
    fetch("https://www.wikidata.org/w/api.php?" + urlencode({
        "action": "wbgetentities", "format": "json", "props": "claims|sitelinks",
        "sitefilter": "enwiki", "ids": "|".join(qids),
    }), "wikidata_club_claims.json")

    # 3. Each club's official website (Wikidata P856). Clubs link their own
    #    official social accounts on their homepage, which is the most
    #    trustworthy source for "which account is the official one".
    entities = pd.read_json(RAW / "wikidata_club_claims.json", typ="series")["entities"]
    (RAW / "club_websites").mkdir(exist_ok=True)
    for qid, entity in entities.items():
        sites = [c["mainsnak"]["datavalue"]["value"] for c in entity["claims"].get("P856", [])
                 if "datavalue" in c["mainsnak"]]
        if not sites:
            print(f"  no official website on Wikidata for {qid}")
            continue
        try:
            fetch(sites[-1], f"club_websites/{qid}.html")  # last listed = most recent
        except Exception as error:  # blocked, timeout, TLS error...
            print(f"  FAILED {qid} {sites[-1]}: {error}")


if __name__ == "__main__":
    main()
