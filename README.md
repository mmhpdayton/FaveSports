# Dayton Sports V12 — Automated Data Build

V12 keeps the V11.1 design and adds automated data maintenance.

## What updates automatically
- Public-team schedules, results and broadcast metadata where the ESPN feed supplies it
- Notre Dame football
- Wisconsin volleyball
- Liverpool Premier League
- Packers, Bills and Colts
- Cubs, including the full 162-game regular season
- Premier League, NFC North, AFC East, AFC South and NL Central standings
- AP Top 25 and Coaches Poll when a valid current rankings feed is available
- AVCA volleyball rankings when a valid rankings feed is available
- Upcoming & Where to Watch is rebuilt from the refreshed schedules

## What remains curated
- Payton JV volleyball
- Amundsen JV football
Those two schedules remain in sports-data.json because JV public feeds are not reliable enough to overwrite your known-good data.

## Refresh cadence
GitHub Actions runs every 3 hours at :15, and you can also run it manually:
GitHub repo → Actions → Update Dayton Sports Data → Run workflow.

The workflow commits sports-data.json and sports-data.js only when something changed.

## Important upload note
The ZIP includes:
`.github/workflows/update-data.yml`

macOS Finder normally hides folders beginning with a dot. If your GitHub upload misses the `.github` folder, use the visible `WORKFLOW-COPY-update-data.yml` file:
1. In GitHub, create `.github/workflows/update-data.yml`
2. Paste the contents of `WORKFLOW-COPY-update-data.yml`
3. Commit it

Once that workflow exists in the repo, the automation is live.

## Safety
The updater uses last-good-data behavior. If a source is unavailable or returns an obviously incomplete season, V12 preserves the existing schedule/ranking/standings data rather than replacing it with bad data.
