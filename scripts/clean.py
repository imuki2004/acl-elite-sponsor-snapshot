"""Clean the extracted tables in data/interim/ and write analysis-ready CSVs.

What this script does:
  1. Standardises club and country names (one spelling everywhere)
  2. Converts numbers stored as text ("1,214", "30.000", "1.2M") to integers
  3. Aggregates home attendance per club (league stage, see ATTENDANCE RULES)
  4. Flags suspicious values in a 'flag' column
  5. Cross-checks our match attendance against Transfermarkt's stadium totals
  6. Prints a short data-quality summary

Inputs  (data/interim/):  matches_raw.csv, clubs_raw.csv, tm_stadium_attendance_raw.csv
Outputs (data/clean/):    matches.csv, clubs.csv, attendance_crosscheck.csv

Run from the project root:
    python scripts/clean.py

ATTENDANCE RULES (decided 2026-11-19, "option A"):
  - Main attendance metrics use LEAGUE-STAGE HOME matches only (4 per club),
    so every club is measured on the same basis.
  - Home matches at a neutral venue (Tractor in Doha) are excluded from the
    averages, because they don't reflect the club's own crowd. They stay in
    matches.csv with a flag.
  - East round-of-16 home legs are reported in separate r16_* columns.
    West R16 and all later rounds were centralised in Jeddah (neutral) and
    are not counted as home matches.
"""

from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
CLEAN = ROOT / "data" / "clean"

# --------------------------------------------------------------------------
# 1. Standard names
# --------------------------------------------------------------------------
# One display name per club, keyed by the stable Wikipedia-based club_key.
# Rule: common English name, "Al" followed by a space (no hyphen).
CLUB_NAMES = {
    "Al_Hilal_SFC": "Al Hilal",
    "Al-Ahli_Saudi_FC": "Al Ahli",
    "Al-Ittihad_Club_(Jeddah)": "Al Ittihad",
    "Tractor_S.C.": "Tractor",
    "Al_Wahda_FC": "Al Wahda",
    "Shabab_Al_Ahli_Club": "Shabab Al Ahli",
    "Sharjah_FC": "Sharjah",
    "Al-Duhail_SC": "Al Duhail",
    "Al_Sadd_SC": "Al Sadd",
    "Al-Gharafa_SC": "Al Gharafa",
    "Al-Shorta_SC": "Al Shorta",
    "FC_Nasaf": "Nasaf",
    "FC_Machida_Zelvia": "Machida Zelvia",
    "Vissel_Kobe": "Vissel Kobe",
    "Sanfrecce_Hiroshima": "Sanfrecce Hiroshima",
    "Buriram_United_F.C.": "Buriram United",
    "Melbourne_City_FC": "Melbourne City",
    "Johor_Darul_Ta'zim_F.C.": "Johor Darul Ta'zim",
    "FC_Seoul": "FC Seoul",
    "Gangwon_FC": "Gangwon FC",
    "Ulsan_HD_FC": "Ulsan HD",
    "Chengdu_Rongcheng_F.C.": "Chengdu Rongcheng",
    "Shanghai_Shenhua_F.C.": "Shanghai Shenhua",
    "Shanghai_Port_F.C.": "Shanghai Port",
}

# Different sources write countries differently; map them all to one spelling.
COUNTRY_NAMES = {
    "Korea Republic": "South Korea",
    "Republic of Korea": "South Korea",
    "UAE": "United Arab Emirates",
    "IR Iran": "Iran",
    "China PR": "China",
    "KSA": "Saudi Arabia",
}

# Home matches that were not played in the club's own country/city.
NEUTRAL_VENUE_MARKERS = ["(Qatar)"]  # Tractor's 'home' match in Doha


# --------------------------------------------------------------------------
# 2. Text -> number
# --------------------------------------------------------------------------
def to_int(value) -> "int | None":
    """Convert a number written as text to an integer.

    Handles:
      '1,214'  -> 1214     (comma thousands, Wikipedia)
      '30.000' -> 30000    (dot thousands, Transfermarkt - NOT 30.0!)
      '1.2M'   -> 1200000  ('K', 'M', 'B' suffixes, social media)
      '12.3万' -> 123000   (Chinese 万 = 10,000 and 亿 = 100,000,000; Weibo/Douyin)
      '−4'     -> -4       (Unicode minus sign, Wikipedia goal difference)
      '+11'    -> 11
      ''/NaN   -> None
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace("−", "-").replace(" ", "").replace(" ", "")
    text = re.sub(r"\[[^\]]*\]", "", text)  # footnote markers like [1]
    if text in ("", "-", "—", "–"):
        return None

    suffix = re.fullmatch(r"([+-]?\d+(?:[.,]\d+)?)([KkMmBb万亿])", text)
    if suffix:
        number = float(suffix.group(1).replace(",", "."))
        multiplier = {"k": 1e3, "m": 1e6, "b": 1e9, "万": 1e4, "亿": 1e8}[suffix.group(2).lower()]
        return round(number * multiplier)

    # Thousands separators: groups of exactly 3 digits after ',' or '.'
    if re.fullmatch(r"[+-]?\d{1,3}([.,]\d{3})+", text):
        return int(re.sub(r"[.,]", "", text))

    try:
        return round(float(text))
    except ValueError:
        raise ValueError(f"Can't convert {value!r} to a number") from None


def venue_name(venue: str) -> str:
    """'Rashid Stadium, Dubai[note 1]' -> 'Rashid Stadium'."""
    return re.sub(r"\[[^\]]*\]", "", venue).split(",")[0].strip()


def add_flag(df: pd.DataFrame, mask: pd.Series, message: str) -> None:
    """Append a message to the 'flag' column for rows where mask is True."""
    df.loc[mask, "flag"] = df.loc[mask, "flag"].where(
        df.loc[mask, "flag"] == "", df.loc[mask, "flag"] + "; ") + message


# --------------------------------------------------------------------------
# 3. Tables
# --------------------------------------------------------------------------
def clean_matches(raw: pd.DataFrame) -> pd.DataFrame:
    m = raw.copy()
    m["home_club"] = m["home_club_key"].map(CLUB_NAMES)
    m["away_club"] = m["away_club_key"].map(CLUB_NAMES)
    m["attendance"] = m["attendance_raw"].map(to_int).astype("Int64")
    m["venue_name"] = m["venue"].map(venue_name)
    m["is_neutral_venue"] = (
        m["venue"].apply(lambda v: any(marker in v for marker in NEUTRAL_VENUE_MARKERS))
        | m["round"].isin(["Quarter-finals", "Semi-finals", "Final"])
        # West R16 was a single match in Jeddah, not a home/away tie
        | ((m["round"] == "Round of 16") & m["date"].str.startswith("2026-04"))
    )
    m["flag"] = ""
    return m


def clean_clubs(raw: pd.DataFrame) -> pd.DataFrame:
    c = raw.copy()
    c["club"] = c["club_key"].map(CLUB_NAMES)
    c["country"] = c["country_raw"].replace(COUNTRY_NAMES)
    c["capacity"] = c["capacity_raw"].map(to_int).astype("Int64")
    return c


def club_attendance(matches: pd.DataFrame, clubs: pd.DataFrame) -> pd.DataFrame:
    """Per club: league-stage home attendance + East R16 home legs."""
    home = matches[(matches["round"] == "League stage") & ~matches["is_neutral_venue"]]
    league = home.groupby("home_club_key").agg(
        home_matches=("attendance", "size"),
        total_attendance=("attendance", "sum"),
        avg_attendance=("attendance", "mean"),
        max_attendance=("attendance", "max"),
        min_attendance=("attendance", "min"),
    )
    # Which match had the highest crowd (useful for the sources sheet)
    top = home.loc[home.groupby("home_club_key")["attendance"].idxmax()]
    league["max_attendance_match_id"] = top.set_index("home_club_key")["match_id"]
    league["avg_attendance"] = league["avg_attendance"].round().astype("Int64")

    neutral = matches[(matches["round"] == "League stage") & matches["is_neutral_venue"]]
    league["neutral_venue_matches_excluded"] = (
        neutral.groupby("home_club_key").size().reindex(league.index).fillna(0).astype(int))

    r16 = matches[(matches["round"] == "Round of 16") & ~matches["is_neutral_venue"]]
    league["r16_home_matches"] = r16.groupby("home_club_key").size().reindex(league.index).fillna(0).astype(int)
    league["r16_home_attendance"] = (
        r16.groupby("home_club_key")["attendance"].sum().reindex(league.index).astype("Int64"))

    out = clubs.merge(league, left_on="club_key", right_index=True, how="left")
    out["capacity_utilisation"] = (out["avg_attendance"] / out["capacity"]).astype(float).round(3)
    return out


def crosscheck_transfermarkt(matches: pd.DataFrame, tm_raw: pd.DataFrame) -> pd.DataFrame:
    """Compare our per-stadium totals (all stages) with Transfermarkt's.

    Uses the stadium crosswalk to translate Wikipedia names to Transfermarkt names.
    Big differences mean one source is missing matches or has different numbers.
    """
    xwalk = pd.read_csv(ROOT / "data" / "reference" / "stadium_crosswalk.csv", dtype=str)
    xwalk = xwalk[xwalk["capacity_source"] == "transfermarkt"]
    wiki_to_tm = dict(zip(xwalk["wiki_venue"].str.lower(), xwalk["source_stadium_name"]))
    # Secondary/neutral venues: not anyone's main stadium, but in both sources
    wiki_to_tm.update({
        "prince abdullah al-faisal sports city stadium": "Prince Abdullah al-Faisal Stadium",
        "mokdong stadium": "Seoul Mokdong Stadium",
        "al-madina international stadium": "Al-Madina Stadium",
    })

    ours = matches.assign(tm_stadium=matches["venue_name"].str.lower().map(wiki_to_tm))
    ours = ours.dropna(subset=["tm_stadium"]).groupby("tm_stadium").agg(
        our_matches=("attendance", "size"), our_total=("attendance", "sum"))

    tm = tm_raw.assign(tm_total=tm_raw["spectators_raw"].map(to_int),
                       tm_average=tm_raw["average_raw"].map(to_int)).set_index("stadium")
    tm["tm_matches_implied"] = (tm["tm_total"] / tm["tm_average"]).round().astype("Int64")

    check = tm[["tm_total", "tm_average", "tm_matches_implied"]].join(ours, how="outer")
    check["difference"] = check["our_total"] - check["tm_total"]
    check["status"] = "match"
    check.loc[check["difference"] != 0, "status"] = "differs"
    check.loc[check["our_total"].isna(), "status"] = "only on Transfermarkt"
    check.loc[check["tm_total"].isna(), "status"] = "only in our data"
    return check.reset_index(names="tm_stadium")


# --------------------------------------------------------------------------
# 4. Flags + summary
# --------------------------------------------------------------------------
def flag_matches(m: pd.DataFrame, clubs: pd.DataFrame) -> None:
    add_flag(m, m["attendance"].isna(), "attendance missing")
    add_flag(m, m["attendance"] == 0, "attendance is zero")
    add_flag(m, (m["round"] == "League stage") & m["is_neutral_venue"],
             "home match at neutral venue - excluded from club averages")

    main = clubs.set_index("club_key")[["home_stadium", "capacity"]]
    m["home_main_stadium"] = m["home_club_key"].map(main["home_stadium"])
    m["home_capacity"] = m["home_club_key"].map(main["capacity"])
    at_main = m["venue_name"].str.lower() == m["home_main_stadium"].str.lower()
    league = m["round"] == "League stage"
    add_flag(m, league & ~at_main & ~m["is_neutral_venue"], "played at secondary home venue")
    add_flag(m, at_main & (m["attendance"] > m["home_capacity"]), "attendance > stadium capacity")
    add_flag(m, at_main & (m["attendance"] < 0.05 * m["home_capacity"]),
             "attendance < 5% of capacity (check)")


def flag_clubs(c: pd.DataFrame) -> None:
    c["flag"] = ""
    add_flag(c, c["capacity_utilisation"] > 1, "average attendance > capacity")
    add_flag(c, c["neutral_venue_matches_excluded"] > 0,
             "neutral-venue home match excluded from averages")
    add_flag(c, c["other_home_venues"].fillna("") != "", "used more than one home venue")
    add_flag(c, c["capacity_source"] == "wikipedia_stadium_page",
             "capacity from Wikipedia (not in Transfermarkt)")


def summary(matches: pd.DataFrame, clubs: pd.DataFrame, check: pd.DataFrame) -> None:
    print("=" * 60)
    print("DATA-QUALITY SUMMARY")
    print("=" * 60)
    print(f"Matches: {len(matches)}  |  Clubs: {len(clubs)}")
    print("\nUnmapped club names:",
          int(matches["home_club"].isna().sum() + clubs["club"].isna().sum()))
    print("\nMissing values in clubs table:")
    missing = clubs.isna().sum()
    print(missing[missing > 0].to_string() if missing.any() else "  none")
    print("\nMatch flags:")
    print(matches.loc[matches["flag"] != "", "flag"].str.split("; ").explode()
          .value_counts().to_string())
    print("\nClub flags:")
    print(clubs.loc[clubs["flag"] != "", ["club", "flag"]].to_string(index=False))
    print("\nTransfermarkt cross-check (stadium totals):")
    print(check["status"].value_counts().to_string())
    print("=" * 60)


def main() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    matches = clean_matches(pd.read_csv(INTERIM / "matches_raw.csv", dtype=str).fillna(""))
    clubs = clean_clubs(pd.read_csv(INTERIM / "clubs_raw.csv", dtype=str).fillna(""))
    tm = pd.read_csv(INTERIM / "tm_stadium_attendance_raw.csv", dtype=str)

    flag_matches(matches, clubs)
    clubs = club_attendance(matches, clubs)
    flag_clubs(clubs)
    check = crosscheck_transfermarkt(matches, tm)

    match_cols = ["match_id", "stage", "round", "date", "home_club", "away_club", "score",
                  "penalties", "venue_name", "attendance", "is_neutral_venue",
                  "home_main_stadium", "home_capacity", "report_url", "flag"]
    club_cols = ["club", "country", "region", "home_stadium", "capacity", "capacity_source",
                 "home_matches", "total_attendance", "avg_attendance", "max_attendance",
                 "min_attendance", "max_attendance_match_id", "capacity_utilisation",
                 "neutral_venue_matches_excluded", "r16_home_matches", "r16_home_attendance",
                 "other_home_venues", "club_key", "flag"]
    matches[match_cols].to_csv(CLEAN / "matches.csv", index=False)
    clubs[club_cols].to_csv(CLEAN / "clubs.csv", index=False)
    check.to_csv(CLEAN / "attendance_crosscheck.csv", index=False)

    summary(matches, clubs, check)
    for name in ["matches.csv", "clubs.csv", "attendance_crosscheck.csv"]:
        print(f"Wrote {CLEAN / name}")


if __name__ == "__main__":
    main()
