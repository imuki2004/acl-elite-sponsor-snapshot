# data/raw — original source files

These files are kept **exactly as downloaded**. Nothing here is edited by hand
or overwritten by any script except `scripts/fetch_raw.sh --force`.
Every download is recorded in [`fetch_log.csv`](fetch_log.csv) (time in UTC,
HTTP status, size, SHA-256 checksum, URL).

## How the files were obtained

All files were downloaded on **2026-11-19** with `curl` and a normal desktop
browser User-Agent. You can repeat the download with:

```bash
bash scripts/fetch_raw.sh
```

| File | Source | What it contains | Wikipedia revision |
|---|---|---|---|
| `wiki_league_stage.html` | [Wikipedia – 2025–26 ACL Elite league stage](https://en.wikipedia.org/wiki/2025%E2%80%9326_AFC_Champions_League_Elite_league_stage) | 96 match boxes: date, home/away team, score, venue, **attendance**, link to the official AFC match report | [oldid 1382916729](https://en.wikipedia.org/w/index.php?oldid=1382916729) |
| `wiki_acle.html` | [Wikipedia – 2025–26 AFC Champions League Elite](https://en.wikipedia.org/wiki/2025%E2%80%9326_AFC_Champions_League_Elite) | Qualified teams, league tables, overall results | [oldid 1375511618](https://en.wikipedia.org/w/index.php?oldid=1375511618) |
| `wiki_knockout_stage.html` | [Wikipedia – 2025–26 ACL Elite knockout stage](https://en.wikipedia.org/wiki/2025%E2%80%9326_AFC_Champions_League_Elite_knockout_stage) | Round of 16 (home and away legs) and the centralised finals | [oldid 1363036612](https://en.wikipedia.org/w/index.php?oldid=1363036612) |
| `tm_acle_attendance_2025.html` | [Transfermarkt – ACL Elite attendance 25/26](https://www.transfermarkt.com/afc-champions-league-elite/besucherzahlen/pokalwettbewerb/ACLE/saison_id/2025) | Attendance **by stadium** for the whole competition: capacity, total spectators, average | — |
| `wiki_stadium_jassim_bin_hamad.html` | [Wikipedia – Jassim bin Hamad Stadium](https://en.wikipedia.org/wiki/Jassim_bin_Hamad_Stadium) | Capacity (infobox). Home of Al Sadd, missing from the Transfermarkt table | [oldid 1385277411](https://en.wikipedia.org/w/index.php?oldid=1385277411) |
| `wiki_stadium_abdullah_bin_khalifa.html` | [Wikipedia – Abdullah bin Khalifa Stadium](https://en.wikipedia.org/wiki/Abdullah_bin_Khalifa_Stadium) | Capacity (infobox). Home of Al-Duhail, missing from Transfermarkt | [oldid 1385459817](https://en.wikipedia.org/w/index.php?oldid=1385459817) |
| `wiki_stadium_rashid.html` | [Wikipedia – Rashid Stadium](https://en.wikipedia.org/wiki/Rashid_Stadium) | Capacity (infobox). Home of Shabab Al Ahli, missing from Transfermarkt | [oldid 1384819846](https://en.wikipedia.org/w/index.php?oldid=1384819846) |

### Stadium capacity: which source?
Capacity comes from **Transfermarkt** when the stadium is in its ACL Elite
table. Otherwise it comes from the stadium's **Wikipedia infobox**. Transfermarkt
often uses sponsor names (e.g. *NOEVIR Stadium Kobe* = *Kobe City Misaki Park
Stadium*), so a hand-made lookup table links the two:
[`data/reference/stadium_crosswalk.csv`](../reference/stadium_crosswalk.csv).
It contains names and sources only. Every capacity number is read from the
raw files by `scripts/parse_raw.py`.

### Why Wikipedia for match-level attendance?
Wikipedia is not the original source of the numbers. Each match box cites
the official **the-afc.com match report**, and we keep that link (`report_url`)
for every match so each attendance figure traces back to the AFC.
Transfermarkt only gives attendance per *stadium*, not per club or match, so we
use it as a **cross-check** and not as the main source.

## Sources that did not work

| Source | Result | What we did |
|---|---|---|
| worldfootball.net (`/attendance/afc-champions-league-2025-2026/1/`) | **Blocked**: HTTP 403, Cloudflare "Just a moment…" bot challenge. The block page held no data and was deleted. | Not used. A manual template can be provided if needed. |
| the-afc.com match pages | Download works (HTTP 200), but the page content is built by JavaScript, so the attendance is **not in the downloaded HTML**. | Report URLs are kept as the cited source. They are not scraped. |
| Transfermarkt with code `ACL` | Wrong competition: `ACL` is the *CAF* (African) Champions League. | Use code `ACLE` instead. |

## Social-media accounts (handles)

Downloaded by `python scripts/fetch_social_handles.py` (logged in `fetch_log.csv`).

| File | Source | What it contains |
|---|---|---|
| `wikidata_club_ids.json` | Wikipedia API (`prop=pageprops`) | Club article → Wikidata item id (Q-number) |
| `wikidata_club_claims.json` | Wikidata API (`wbgetentities`) | Club facts incl. official website (P856), Instagram (P2003), TikTok (P7085), YouTube channel (P2397), X (P2002) |
| `club_websites/Q….html` | Each club's official homepage (URL from Wikidata P856) | Homepage HTML. Clubs link their official social accounts here |

Homepages that **could not be downloaded**: Al Wahda (403), FC Seoul (403),
Gangwon FC (503), Sanfrecce Hiroshima (503), Johor Darul Ta'zim (403).
Chengdu Rongcheng has no official website on Wikidata. The Nasaf, Sharjah,
Shanghai Port and Shanghai Shenhua homepages downloaded but contain no social
links (pages built by JavaScript, or redirects).

## Digital followers: entered by hand

Instagram, TikTok, YouTube and X block automated access, so follower counts
are **collected manually** in [`digital_followers_manual.csv`](digital_followers_manual.csv).
The file was generated by `scripts/make_followers_template.py`, which never
overwrites it.

**How to fill it in.** For each row:
1. Open `account_url`. If `handle_source` is `not_found`, search the platform.
   Only use an account that is clearly official (verified badge, or linked
   from the club's website), and fill in `handle` and `account_url`.
2. Read `handle_note`. It warns when sources disagree.
3. Enter `followers` exactly as shown (`1.2M`, `45.3K` and `45,312` all work;
   `clean.py` converts them).
4. Enter `date_collected` as `YYYY-MM-DD`.
5. Leave `followers` **empty** if the club has no official account on that
   platform, and write why in `collector_notes`. Never estimate.

### Collected data: `digital_followers_filled.csv`
The template filled in by hand on **2026-11-19** (102 rows). It is the file
`clean.py` reads. `digital_followers_manual.csv` is the empty template it
started from. Each row's `collector_notes` records precision (`exact` or
`rounded_by_platform`) and whether the account has a verified badge.

`clean.py` applies these rules (see `account_status` in
`data/clean/digital_followers.csv`):
- **No official account → 0.**
- **Unverified accounts are excluded (0):** every `research_check` account, plus
  Wikidata-only accounts marked "not verified" (Al Duhail and Ulsan TikTok).
  Accounts linked from a club's own website count even without a badge.
  This removes 11 accounts and 495,575 followers, mainly JDT TikTok (311K).
  Switch it off with `EXCLUDE_UNVERIFIED = False`.
- **Douyin → 0, status `not_checked`.** Douyin search needs a Chinese phone login.

### Finding the accounts that were missing

`python scripts/lookup_youtube_channels.py` writes **`youtube_channel_lookup.csv`**.
YouTube pages load without a login, so this script:
- resolves every known YouTube link to its channel id. This showed that the
  website and Wikidata links for Al Hilal, Buriram, Machida and Ulsan are the
  **same channel**.
- searches YouTube for clubs without a channel and records whether each result
  has the **verified badge**.

Accounts chosen through this lookup or through web search are recorded by
hand, with evidence, in
[`data/reference/social_handles_research.csv`](../reference/social_handles_research.csv):
- `confirmed` means strong evidence, such as the YouTube verified badge.
- `check` means likely, but please confirm before entering numbers.

TikTok, Instagram and X block automated checks, so their gaps remain
`not_found`.

### Mainland-China clubs: Weibo and Douyin
Chengdu Rongcheng, Shanghai Port and Shanghai Shenhua mostly use Chinese
platforms, because Instagram, TikTok, YouTube and X are blocked in China. The
template therefore has extra **`weibo`** rows (account ids from Wikidata,
property P3579) and **`douyin`** rows (search by the Chinese club name) for these
3 clubs only. They are marked `counts_in_core_total = no`:
- `total_digital_followers` uses only the 4 core platforms, so all 24 clubs
  are compared on the same platforms.
- Weibo/Douyin followers are reported in separate columns.

Weibo shows counts like `12.3万` (万 = 10,000). Enter them as shown; `clean.py`
converts them.
