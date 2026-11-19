"""Turn the raw HTML pages in data/raw/ into structured CSV tables.

This step only *extracts*: values are written as text exactly as they appear
on the page (e.g. "1,214", "4–3"). Converting to numbers, standardising names
and adding calculated columns happens later in scripts/clean.py.

Inputs  (data/raw/):
    wiki_league_stage.html       -> 96 league-stage matches
    wiki_knockout_stage.html     -> knockout matches
    tm_acle_attendance_2025.html -> Transfermarkt attendance by stadium

Outputs (data/interim/):
    matches_raw.csv              one row per match (league + knockout)
    tm_stadium_attendance_raw.csv one row per stadium

Run from the project root:
    python scripts/parse_raw.py
"""

from io import StringIO
from pathlib import Path
import re

import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"

WIKI_PAGES = {
    "league_stage": "wiki_league_stage.html",
    "knockout_stage": "wiki_knockout_stage.html",
}


def clean_text(element) -> str:
    """Visible text of an HTML element, whitespace squashed to single spaces."""
    if element is None:
        return ""
    return re.sub(r"\s+", " ", element.text_content()).strip()


def first(nodes):
    return nodes[0] if nodes else None


def parse_football_boxes(path: Path, stage: str) -> list[dict]:
    """Extract every Wikipedia 'football box' (one box = one match).

    Each box looks like this on the page:
        date | Home team  score  Away team | venue / Attendance: N / Referee
    and contains a 'Report' link to the official the-afc.com match page.
    """
    doc = html.parse(str(path)).getroot()
    boxes = doc.xpath('//div[contains(concat(" ", @class, " "), " footballbox ")]')
    rows = []
    for box in boxes:
        right = first(box.xpath('.//div[@class="fright"]'))  # venue + attendance block
        venue, attendance, referee = "", "", ""
        if right is not None:
            venue = clean_text(first(right.xpath('./div[@itemprop="location"]')))
            for line in right.xpath("./div"):
                text = clean_text(line)
                if text.startswith("Attendance:"):
                    attendance = text.removeprefix("Attendance:").strip()
                elif text.startswith("Referee:"):
                    referee = text.removeprefix("Referee:").strip()

        # The first link that leaves Wikipedia is the official match report.
        external = [
            a.get("href") for a in box.xpath(".//a[@href]")
            if "wikipedia.org" not in a.get("href") and "wikimedia.org" not in a.get("href")
        ]

        rows.append({
            "stage": stage,
            "match_id": box.get("id", ""),
            "date": clean_text(first(box.xpath('.//span[contains(@class, "dtstart")]'))),
            "round": clean_text(first(box.xpath('.//div[contains(@class, "frnd")]'))),
            "home_team": clean_text(first(box.xpath('.//th[@class="fhome"]'))),
            "score": clean_text(first(box.xpath('.//th[@class="fscore"]'))),
            "away_team": clean_text(first(box.xpath('.//th[@class="faway"]'))),
            "venue": venue,
            "attendance_raw": attendance,
            "referee": referee,
            "report_url": external[0] if external else "",
            "source_file": path.name,
        })
    return rows


def parse_transfermarkt_stadiums(path: Path) -> pd.DataFrame:
    """Extract the Transfermarkt 'attendance by stadium' table.

    Transfermarkt writes numbers with '.' as thousands separator (79.717 = 79,717),
    so everything is read as text here to avoid pandas misreading them as decimals.
    """
    as_text = {col: str for col in ["#", "Stadium", "Capacity", "Spectators", "Average"]}
    tables = pd.read_html(StringIO(path.read_text(encoding="utf-8")), converters=as_text)
    table = next(t for t in tables if "Stadium" in t.columns)
    table = table.rename(columns={
        "#": "rank", "Stadium": "stadium", "Capacity": "capacity_raw",
        "Spectators": "spectators_raw", "Average": "average_raw",
    })
    table = table[table["stadium"] != "Total:"]  # drop the summary row
    table["source_file"] = path.name
    return table


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)

    match_rows = []
    for stage, filename in WIKI_PAGES.items():
        rows = parse_football_boxes(RAW / filename, stage)
        print(f"{filename}: {len(rows)} matches")
        match_rows.extend(rows)
    matches = pd.DataFrame(match_rows)
    matches.to_csv(INTERIM / "matches_raw.csv", index=False)

    stadiums = parse_transfermarkt_stadiums(RAW / "tm_acle_attendance_2025.html")
    stadiums.to_csv(INTERIM / "tm_stadium_attendance_raw.csv", index=False)
    print(f"tm_acle_attendance_2025.html: {len(stadiums)} stadiums")

    # Quick checks so problems are visible straight away
    print("\nChecks:")
    print("  matches without attendance:", (matches["attendance_raw"] == "").sum())
    print("  matches without AFC report link:", (matches["report_url"] == "").sum())
    league = matches[matches["stage"] == "league_stage"]
    print("  league-stage clubs found:", pd.concat([league.home_team, league.away_team]).nunique())
    print(f"\nWrote {INTERIM / 'matches_raw.csv'}")
    print(f"Wrote {INTERIM / 'tm_stadium_attendance_raw.csv'}")


if __name__ == "__main__":
    main()
