"""Build output/acl_sponsor_snapshot.xlsx from the cleaned data.

Sheets (all flat tables for Looker Studio: one header row, snake_case
columns, no merged cells, no blank rows):
  clubs      one row per club, all metrics (dashboard source)
  countries  aggregated by country
  sources    every number -> source URL + date collected
  notes      assumptions, gaps and data-quality flags

Run from the project root (after clean.py):
    python scripts/build_excel.py
"""

from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "output" / "acl_sponsor_snapshot.xlsx"

# Permanent links to the exact page versions used (see data/raw/README.md)
PAGES = {
    "wiki_league_stage.html": ("Wikipedia: 2025-26 ACL Elite league stage",
                               "https://en.wikipedia.org/w/index.php?oldid=1382916729"),
    "wiki_acle.html": ("Wikipedia: 2025-26 AFC Champions League Elite",
                       "https://en.wikipedia.org/w/index.php?oldid=1375511618"),
    "wiki_knockout_stage.html": ("Wikipedia: 2025-26 ACL Elite knockout stage",
                                 "https://en.wikipedia.org/w/index.php?oldid=1363036612"),
    "tm_acle_attendance_2025.html": ("Transfermarkt: ACL Elite 25/26 attendance by stadium",
                                     "https://www.transfermarkt.com/afc-champions-league-elite/"
                                     "besucherzahlen/pokalwettbewerb/ACLE/saison_id/2025"),
    "wiki_stadium_jassim_bin_hamad.html": ("Wikipedia: Jassim bin Hamad Stadium",
                                           "https://en.wikipedia.org/w/index.php?oldid=1385277411"),
    "wiki_stadium_abdullah_bin_khalifa.html": ("Wikipedia: Abdullah bin Khalifa Stadium",
                                               "https://en.wikipedia.org/w/index.php?oldid=1385459817"),
    "wiki_stadium_rashid.html": ("Wikipedia: Rashid Stadium",
                                 "https://en.wikipedia.org/w/index.php?oldid=1384819846"),
}

STAGE_ORDER = ["League stage", "Round of 16", "Quarter-finals", "Semi-finals", "Runner-up", "Winner"]


def fetch_dates() -> dict:
    """Raw file name -> date it was downloaded (YYYY-MM-DD), from fetch_log.csv."""
    log = pd.read_csv(RAW / "fetch_log.csv")
    return log.groupby("file")["fetched_at_utc"].max().str[:10].to_dict()


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------
def countries_sheet(clubs: pd.DataFrame) -> pd.DataFrame:
    g = clubs.groupby("country")
    out = pd.DataFrame({
        "region": g["region"].first(),
        "clubs": g.size(),
        "club_names": g["club"].apply(lambda s: ", ".join(sorted(s))),
        "home_matches": g["home_matches"].sum(),
        "total_attendance": g["total_attendance"].sum(),
        "total_capacity": g["capacity"].sum(),
        "total_digital_followers": g["total_digital_followers"].sum(),
        "core_platform_followers": g["core_platform_followers"].sum(),
        "china_platform_followers": g["china_platform_followers"].sum(min_count=1),
        "league_points": g["league_points"].sum(),
        "league_won": g["league_won"].sum(),
        "league_drawn": g["league_drawn"].sum(),
        "league_lost": g["league_lost"].sum(),
        "clubs_advanced_to_r16": g["advanced_to_r16"].sum(),
    })
    # Averages are weighted by matches, not an average of club averages
    out["avg_attendance"] = (out["total_attendance"] / out["home_matches"]).round().astype(int)
    seats_offered = (clubs["capacity"] * clubs["home_matches"]).groupby(clubs["country"]).sum()
    out["capacity_utilisation"] = (out["total_attendance"] / seats_offered).round(3)
    out["avg_digital_followers_per_club"] = (out["total_digital_followers"] / out["clubs"]).round().astype(int)
    # Same definition as the clubs sheet: followers per average home fan
    out["followers_per_fan"] = (out["total_digital_followers"]
                                / g["avg_attendance"].sum()).round(1)
    best = g["furthest_stage_order"].max()
    out["best_furthest_stage"] = best.map(lambda i: STAGE_ORDER[i - 1])
    out["best_furthest_stage_order"] = best
    cols = ["region", "clubs", "club_names", "home_matches", "total_attendance", "avg_attendance",
            "total_capacity", "capacity_utilisation", "total_digital_followers",
            "core_platform_followers", "china_platform_followers", "avg_digital_followers_per_club",
            "followers_per_fan", "league_points", "league_won", "league_drawn", "league_lost",
            "clubs_advanced_to_r16", "best_furthest_stage", "best_furthest_stage_order"]
    return (out[cols].reset_index().sort_values("total_digital_followers", ascending=False)
            .reset_index(drop=True))


def sources_sheet(clubs, matches, followers, dates) -> pd.DataFrame:
    """One row per number in the dataset: what it is, its value, where it came from."""
    rows = []

    def add(metric, club, detail, value, source_name, source_url, date, notes=""):
        rows.append({"metric": metric, "club": club, "detail": detail, "value": value,
                     "source_name": source_name, "source_url": source_url,
                     "date_collected": date, "notes": notes})

    # Club info + league table: Wikipedia main page
    name, url = PAGES["wiki_acle.html"]
    for _, c in clubs.iterrows():
        add("country, region", c["club"], "", f"{c['country']}, {c['region']}", name, url,
            dates["wiki_acle.html"])
        add("league table (position, W/D/L, goals, points)", c["club"], "",
            f"pos {c['league_position']}, {c['league_points']} pts", name, url, dates["wiki_acle.html"],
            "Points checked against the 96 match scores: all match")

    # Capacity: Transfermarkt or the stadium's Wikipedia page
    xwalk = pd.read_csv(ROOT / "data" / "reference" / "stadium_crosswalk.csv")
    xwalk["key"] = xwalk["wiki_venue"].str.lower()
    for _, c in clubs.iterrows():
        src = xwalk.set_index("key").loc[c["home_stadium"].lower()]
        name, url = PAGES[src["source_file"]]
        add("capacity", c["club"], c["home_stadium"], int(c["capacity"]), name, url,
            dates[src["source_file"]],
            f"listed as '{src['source_stadium_name']}'" if src["source_stadium_name"] != c["home_stadium"] else "")

    # Attendance: every match, official AFC match report (via Wikipedia)
    for _, m in matches.iterrows():
        page = "wiki_league_stage.html" if m["stage"] == "league_stage" else "wiki_knockout_stage.html"
        add("attendance", m["home_club"], f"{m['round']}: {m['home_club']} v {m['away_club']} ({m['date']})",
            m["attendance"], "AFC official match report (figure as cited on Wikipedia)",
            m["report_url"], dates[page], f"Read from {PAGES[page][1]}")

    # Followers: one row per club x platform
    for _, f in followers.iterrows():
        has_account = isinstance(f["source_url"], str) and f["source_url"] != ""
        add(f"{f['platform']}_followers", f["club"], f"@{f['handle']}" if f["handle"] else "",
            f["followers_used"],
            f"{f['platform'].capitalize()} profile (collected by hand)" if has_account
            else f"{f['platform'].capitalize()}: manual search, no account counted",
            f["source_url"] if has_account else f"not applicable ({f['account_status']})",
            f["date_collected"],
            f"status: {f['account_status']}; precision: {f['precision'] or 'n/a'}")
    return pd.DataFrame(rows)


def notes_sheet(clubs, matches, followers, crosscheck) -> pd.DataFrame:
    rows = []

    def add(note_type, topic, note, club=""):
        rows.append({"note_type": note_type, "topic": topic, "club": club, "note": note})

    # Assumptions / method
    add("assumption", "attendance",
        "Attendance metrics use league-stage HOME matches only (4 per club) so all clubs are compared "
        "on the same basis. Knockout matches from the West round of 16 onward were centralised in "
        "Jeddah (neutral) and are not home matches.")
    add("assumption", "attendance",
        "East round-of-16 home legs are reported separately (r16_home_matches, r16_home_attendance).")
    add("assumption", "attendance",
        "Tractor's league-stage 'home' match in Doha (neutral venue, security reasons) is excluded "
        "from Tractor's averages: 3 home matches counted.")
    add("assumption", "attendance",
        "Attendance figures are the official AFC match-report numbers as cited on Wikipedia; "
        "the-afc.com pages could not be read automatically (JavaScript).")
    add("assumption", "capacity",
        "Capacity = the club's main home stadium (most-used league-stage venue). Source: Transfermarkt; "
        "Wikipedia stadium infobox for 3 stadiums missing on Transfermarkt.")
    add("assumption", "capacity_utilisation",
        "capacity_utilisation = avg_attendance / capacity of the main stadium, also for clubs that "
        "played one home match at another venue (flagged).")
    add("assumption", "digital",
        "total_digital_followers = sum of all platforms collected: Instagram, TikTok, YouTube, X for "
        "all clubs, plus Weibo for the 3 mainland-China clubs. core_platform_followers = the 4 core "
        "platforms only (like-for-like).")
    add("assumption", "digital",
        "Followers are the sum of accounts, not unique people: one fan following on 3 platforms counts 3 times.")
    add("assumption", "digital",
        "No official account = 0. Unverified accounts are excluded (0); accounts linked from the "
        "club's own website count without a badge.")
    add("assumption", "digital",
        "YouTube, Weibo and large TikTok/X accounts only show rounded counts (e.g. 2.1M); "
        "see 'precision' in the sources sheet.")
    add("assumption", "followers_per_fan",
        "followers_per_fan = total_digital_followers / avg_attendance. High = digital reach far "
        "larger than the stadium crowd.")

    # Gaps
    add("gap", "data source", "worldfootball.net blocked automated access (HTTP 403); not used.")
    add("gap", "digital", "Douyin not checked for the 3 China clubs (needs a Chinese phone login); counted as 0.")
    for _, f in followers[followers["account_status"] == "no_official_account"].iterrows():
        add("gap", f"{f['platform']}_followers", f"No official account found. {f['collector_notes']}", f["club"])
    excluded = followers[followers["account_status"] == "excluded_unverified"]
    for _, f in excluded.iterrows():
        add("gap", f"{f['platform']}_followers",
            f"Unverified account @{f['handle']} ({int(f['followers_reported']):,}) excluded, counted as 0.",
            f["club"])

    # Data-quality flags
    for _, c in clubs[clubs["flag"].notna()].iterrows():
        for flag in c["flag"].split("; "):
            add("flag", "club", flag, c["club"])
    for _, m in matches[matches["flag"].notna()].iterrows():
        for flag in m["flag"].split("; "):
            add("flag", "match", f"{flag}: {m['round']} {m['home_club']} v {m['away_club']} "
                f"({m['date']}), attendance {m['attendance']:,}, capacity {m['home_capacity']:,}",
                m["home_club"])
    for _, x in crosscheck[crosscheck["status"] != "match"].iterrows():
        add("cross-check", "attendance",
            f"Transfermarkt '{x['tm_stadium']}': {x['status']} (ours {x['our_total']}, "
            f"Transfermarkt {x['tm_total']}). Mostly matches assigned to a different stadium; "
            "see data/clean/attendance_crosscheck.csv.")
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Write + format
# --------------------------------------------------------------------------
def format_sheet(ws, df: pd.DataFrame) -> None:
    header_fill = PatternFill("solid", fgColor="DDE3EA")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
    ws.freeze_panes = "B2"
    for i, col in enumerate(df.columns, start=1):
        longest = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)])
        ws.column_dimensions[get_column_letter(i)].width = min(max(10, longest + 2), 60)
        if col in ("capacity_utilisation",):
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                row[0].number_format = "0.0%"
        elif pd.api.types.is_integer_dtype(df[col]) or col.endswith(("_followers", "attendance", "capacity")):
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                row[0].number_format = "#,##0"


def main() -> None:
    clubs = pd.read_csv(CLEAN / "clubs.csv")
    matches = pd.read_csv(CLEAN / "matches.csv")
    followers = pd.read_csv(CLEAN / "digital_followers.csv", keep_default_na=False,
                            na_values=[""]).fillna({"handle": "", "precision": "", "collector_notes": ""})
    crosscheck = pd.read_csv(CLEAN / "attendance_crosscheck.csv")
    dates = fetch_dates()

    sheets = {
        "clubs": clubs.sort_values("total_digital_followers", ascending=False).reset_index(drop=True),
        "countries": countries_sheet(clubs),
        "sources": sources_sheet(clubs, matches, followers, dates),
        "notes": notes_sheet(clubs, matches, followers, crosscheck),
    }
    OUT.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            format_sheet(writer.sheets[name], df)

    for name, df in sheets.items():
        print(f"{name:<10} {len(df):>4} rows x {len(df.columns):>2} columns")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
