#!/usr/bin/env bash
# Download the raw source pages into data/raw/ and log every download.
#
# Usage (from the project root):
#   bash scripts/fetch_raw.sh            # download only files that don't exist yet
#   bash scripts/fetch_raw.sh --force    # re-download everything (overwrites raw files!)
#
# Raw files are never edited by hand or by other scripts. Each download is
# appended to data/raw/fetch_log.csv with its URL, HTTP status, size and SHA-256,
# so you can prove later which exact file the numbers came from.
#
# Wikipedia pages are fetched by *revision id* (oldid=...), so re-running this
# returns the identical page version we used, even if the article changes later.

set -euo pipefail
cd "$(dirname "$0")/.."

RAW=data/raw
LOG=$RAW/fetch_log.csv
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FORCE=${1:-}

[ -f "$LOG" ] || echo "fetched_at_utc,file,http_status,bytes,sha256,url" > "$LOG"

# file name | URL
SOURCES=(
  # League stage: 96 match boxes (date, teams, score, venue, attendance, AFC report link)
  "wiki_league_stage.html|https://en.wikipedia.org/w/index.php?title=2025%E2%80%9326_AFC_Champions_League_Elite_league_stage&oldid=1382916729"
  # Main competition page: team list, standings, overall results
  "wiki_acle.html|https://en.wikipedia.org/w/index.php?title=2025%E2%80%9326_AFC_Champions_League_Elite&oldid=1375511618"
  # Knockout stage: round of 16 (home/away) and centralised finals
  "wiki_knockout_stage.html|https://en.wikipedia.org/w/index.php?title=2025%E2%80%9326_AFC_Champions_League_Elite_knockout_stage&oldid=1363036612"
  # Transfermarkt attendance by stadium (competition code ACLE; code 'ACL' is the CAF Champions League)
  "tm_acle_attendance_2025.html|https://www.transfermarkt.com/afc-champions-league-elite/besucherzahlen/pokalwettbewerb/ACLE/saison_id/2025"
  # Stadium capacities for the 3 home grounds missing from the Transfermarkt table
  "wiki_stadium_jassim_bin_hamad.html|https://en.wikipedia.org/w/index.php?title=Jassim_bin_Hamad_Stadium&oldid=1385277411"
  "wiki_stadium_abdullah_bin_khalifa.html|https://en.wikipedia.org/w/index.php?title=Abdullah_bin_Khalifa_Stadium&oldid=1385459817"
  "wiki_stadium_rashid.html|https://en.wikipedia.org/w/index.php?title=Rashid_Stadium&oldid=1384819846"
)

for entry in "${SOURCES[@]}"; do
  file="${entry%%|*}"; url="${entry#*|}"; out="$RAW/$file"
  if [ -f "$out" ] && [ "$FORCE" != "--force" ]; then
    echo "skip   $file (already exists)"; continue
  fi
  status=$(curl -sL -A "$UA" --max-time 30 -o "$out" -w "%{http_code}" "$url")
  bytes=$(wc -c < "$out" | tr -d ' ')
  sha=$(shasum -a 256 "$out" | cut -d' ' -f1)
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$file,$status,$bytes,$sha,\"$url\"" >> "$LOG"
  echo "$status  $file ($bytes bytes)"
  if [ "$status" != "200" ]; then
    echo "  WARNING: $file returned HTTP $status - site may be blocking; see data/raw/README.md"
  fi
  sleep 2   # be polite to the servers
done
