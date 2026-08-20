# Dayton Sports V13.7

Fixes College Volleyball schedules and changes volleyball to an expand/collapse weekly model.

## Schedule-source fix
The prior volleyball tab was fetching ESPN's default scoreboard payload and then trying to filter it locally. That payload can be incomplete / ranked-team oriented.

V13.7 requests the correct NCAA group directly:
- Top 25 + Wisconsin: full Division I feed (`groups=50`) and then filters ranked teams + Wisconsin locally
- All D-I: `groups=50`
- ACC: `groups=2`
- Big Ten: `groups=7`
- Big 12: `groups=8`
- SEC: `groups=23`
- Big East: `groups=4`
- Atlantic 10: `groups=3`
- MVC: `groups=18`
- Mountain West: `groups=44`
- WCC: `groups=29`

Each query uses `limit=500`.

## Expand/collapse by week
College Volleyball now matches the College Football browsing model:
- current week expanded automatically
- previous weeks collapsed with results
- future weeks collapsed
- tap/click any week to expand it
- no Previous / Next buttons

The tab renders two prior weeks, the current week, and sixteen future weeks.

## Live scoring
Every open volleyball week refreshes automatically every 60 seconds while the College Volleyball tab is active.

## Preserved
- Wisconsin highlighting
- Top 25 default every time the tab is opened
- AVCA Top 25 beneath the schedule
- clickable volleyball game-detail pages
- all V13.5/V13.6 football, MLB, DraftKings, SiriusXM, Amundsen Varsity and Cubs fixes

## Upgrade from V13.6
Replace:
- index.html
- sports-data.json
- sports-data.js

V13.5 `scripts/update_data.py` and `.github/workflows/update-data.yml` remain unchanged.
