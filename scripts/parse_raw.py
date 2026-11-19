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


# Some pages link a club through a Wikipedia redirect, so the same club gets
# different keys. Checked via the Wikipedia API: 'Al-Hilal Saudi FC' redirects
# to the article 'Al Hilal SFC'. The three pages use three spellings of it.
CLUB_KEY_ALIASES = {
    "Al-Hilal_Saudi_FC": "Al_Hilal_SFC",  # league-stage page
    "Al-Hilal_SFC": "Al_Hilal_SFC",       # knockout-stage page
}


def club_key(element) -> str:
    """Stable club ID = the club's Wikipedia article name, e.g. 'Al-Hilal_SFC'.

    Display names differ between pages ('Al Hilal' vs 'Al-Hilal'), but every
    page links to the same article, so we join tables on this key instead.
    The flag icon links to the football association, so we skip those links.
    """
    if element is None:
        return ""
    for a in element.xpath(".//a[@href]"):
        if a.xpath("ancestor::span[contains(@class, 'flagicon')]"):
            continue
        key = a.get("href").rsplit("/wiki/", 1)[-1]
        return CLUB_KEY_ALIASES.get(key, key)
    return ""


def fill_missing_club_keys(matches: pd.DataFrame) -> pd.DataFrame:
    """Wikipedia only links a team the first time it appears in a section, so
    e.g. second legs have a team name but no link. Fill those keys using the
    same team name from rows that do have a link."""
    pairs = pd.concat([
        matches[["home_team", "home_club_key"]].set_axis(["name", "key"], axis=1),
        matches[["away_team", "away_club_key"]].set_axis(["name", "key"], axis=1),
    ])
    name_to_key = pairs[pairs["key"] != ""].drop_duplicates("name").set_index("name")["key"]
    for side in ["home", "away"]:
        missing = matches[f"{side}_club_key"] == ""
        matches.loc[missing, f"{side}_club_key"] = matches.loc[missing, f"{side}_team"].map(name_to_key).fillna("")
    return matches


def strip_footnotes(text: str) -> str:
    """'Rashid Stadium[note 1]' -> 'Rashid Stadium'; '15,000[1]' -> '15,000'."""
    return re.sub(r"\[[^\]]*\]", "", text).strip()


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

        home = first(box.xpath('.//th[@class="fhome"]'))
        away = first(box.xpath('.//th[@class="faway"]'))
        rows.append({
            "stage": stage,
            "match_id": box.get("id", ""),
            "date": clean_text(first(box.xpath('.//span[contains(@class, "dtstart")]'))),
            "home_team": clean_text(home),
            "score": clean_text(first(box.xpath('.//th[@class="fscore"]'))),
            "away_team": clean_text(away),
            "home_club_key": club_key(home),
            "away_club_key": club_key(away),
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


def parse_league_tables(path: Path) -> pd.DataFrame:
    """Extract the West and East league-stage tables from the main ACLE page.

    One row per club: region, position, played, W/D/L, goals, points, and the
    country taken from the flag icon next to the team name.
    """
    doc = html.parse(str(path)).getroot()
    rows = []
    for table in doc.xpath('//table[contains(@class, "wikitable")]'):
        header = [clean_text(th) for th in table.xpath(".//tr[1]/th")]
        if not header or header[0] != "Pos":
            continue
        # The section heading just above the table says which region it is.
        heading = clean_text(first(table.xpath("preceding::*[self::h2 or self::h3][1]")))
        region = "West" if "West" in heading else "East" if "East" in heading else heading
        for tr in table.xpath(".//tr")[1:]:
            cells = tr.xpath("./th|./td")
            values = [clean_text(c) for c in cells]
            team_cell = cells[1]
            flag = first(team_cell.xpath(".//span[contains(@class, 'flagicon')]//img/@alt"))
            rows.append({
                "region": region,
                "club_key": club_key(team_cell),
                "club_name_raw": values[1],
                "country_raw": flag or "",
                "position_raw": values[0],
                "played_raw": values[2], "won_raw": values[3], "drawn_raw": values[4],
                "lost_raw": values[5], "goals_for_raw": values[6],
                "goals_against_raw": values[7], "goal_diff_raw": values[8],
                "points_raw": values[9],
                "qualification_raw": values[10] if len(values) > 10 else "",
                "source_file": path.name,
            })
    return pd.DataFrame(rows)


def parse_stadium_infobox_capacity(path: Path) -> str:
    """Read 'Capacity' from a Wikipedia stadium infobox, e.g. '15,000'."""
    doc = html.parse(str(path)).getroot()
    for tr in doc.xpath('//table[contains(@class, "infobox")]//tr'):
        label = clean_text(first(tr.xpath("./th")))
        if label.lower() == "capacity":
            return strip_footnotes(clean_text(first(tr.xpath("./td"))))
    return ""


def build_clubs(league: pd.DataFrame, matches: pd.DataFrame,
                tm_stadiums: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """One row per club: name, country, region, main home stadium, capacity.

    Main home stadium = the venue a club used most for its league-stage home
    matches. Capacity is looked up via data/reference/stadium_crosswalk.csv,
    either in the Transfermarkt table or in the stadium's Wikipedia infobox.
    """
    home = matches[matches["stage"] == "league_stage"].copy()
    home["venue_name"] = home["venue"].map(lambda v: strip_footnotes(v).split(",")[0].strip())
    home["venue_lower"] = home["venue_name"].str.lower()  # 'Jassim Bin Hamad' == 'Jassim bin Hamad'

    venue_summary = []
    for key, group in home.groupby("home_club_key"):
        counts = group["venue_lower"].value_counts()
        main_lower = counts.index[0]
        venue_summary.append({
            "club_key": key,
            "home_stadium": group.loc[group["venue_lower"] == main_lower, "venue_name"].iloc[0],
            "league_home_matches_at_main_stadium": str(counts.iloc[0]),
            "other_home_venues": "; ".join(
                group.loc[group["venue_lower"] != main_lower, "venue"].unique()),
        })
    clubs = league[["club_key", "club_name_raw", "country_raw", "region"]].merge(
        pd.DataFrame(venue_summary), on="club_key", how="left")

    tm_capacity = dict(zip(tm_stadiums["stadium"], tm_stadiums["capacity_raw"]))
    xwalk = crosswalk.assign(key=crosswalk["wiki_venue"].str.lower()).set_index("key")

    def capacity_for(stadium: str) -> pd.Series:
        if stadium.lower() not in xwalk.index:
            return pd.Series({"capacity_raw": "", "capacity_source": "NOT IN CROSSWALK",
                              "capacity_source_file": ""})
        row = xwalk.loc[stadium.lower()]
        if row["capacity_source"] == "transfermarkt":
            value = tm_capacity.get(row["source_stadium_name"], "")
        else:
            value = parse_stadium_infobox_capacity(RAW / row["source_file"])
        return pd.Series({"capacity_raw": value,
                          "capacity_source": row["capacity_source"],
                          "capacity_source_file": row["source_file"]})

    return pd.concat([clubs, clubs["home_stadium"].apply(capacity_for)], axis=1)


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)

    match_rows = []
    for stage, filename in WIKI_PAGES.items():
        rows = parse_football_boxes(RAW / filename, stage)
        print(f"{filename}: {len(rows)} matches")
        match_rows.extend(rows)
    matches = fill_missing_club_keys(pd.DataFrame(match_rows))
    matches.to_csv(INTERIM / "matches_raw.csv", index=False)

    stadiums = parse_transfermarkt_stadiums(RAW / "tm_acle_attendance_2025.html")
    stadiums.to_csv(INTERIM / "tm_stadium_attendance_raw.csv", index=False)
    print(f"tm_acle_attendance_2025.html: {len(stadiums)} stadiums")

    league = parse_league_tables(RAW / "wiki_acle.html")
    crosswalk = pd.read_csv(ROOT / "data" / "reference" / "stadium_crosswalk.csv", dtype=str).fillna("")
    clubs = build_clubs(league, matches, stadiums, crosswalk)
    clubs.to_csv(INTERIM / "clubs_raw.csv", index=False)
    print(f"wiki_acle.html: {len(clubs)} clubs")

    # Quick checks so problems are visible straight away
    print("\nChecks:")
    print("  matches without attendance:", (matches["attendance_raw"] == "").sum())
    print("  matches without AFC report link:", (matches["report_url"] == "").sum())
    print("  matches without club key:",
          ((matches["home_club_key"] == "") | (matches["away_club_key"] == "")).sum())
    league_matches = matches[matches["stage"] == "league_stage"]
    print("  league-stage clubs in match boxes:",
          pd.concat([league_matches.home_club_key, league_matches.away_club_key]).nunique())
    print("  clubs per region:", clubs["region"].value_counts().to_dict())
    print("  clubs without country:", (clubs["country_raw"] == "").sum())
    print("  clubs without home stadium:", clubs["home_stadium"].isna().sum())
    print("  clubs without capacity:", (clubs["capacity_raw"] == "").sum())
    for name in ["matches_raw.csv", "tm_stadium_attendance_raw.csv", "clubs_raw.csv"]:
        print(f"Wrote {INTERIM / name}")


if __name__ == "__main__":
    main()
