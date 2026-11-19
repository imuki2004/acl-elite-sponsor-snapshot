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

## Still to collect
- Digital followers (Instagram, TikTok, YouTube, X). These platforms block
  automated access, so they will be a manual-entry CSV template.
