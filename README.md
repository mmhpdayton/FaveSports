# Dayton Sports V14.2 — REDO

This replaces the earlier V14.2.

## Visible menu
Home → Schedules → College Football → Premier League → NFL → College Volleyball → Standings

Rankings remains accessible from ranking links but is not in the visible top navigation.

## UX/cosmetic redesign
The full sports-app redesign remains:
- sticky horizontal mobile nav
- Up Next: one active-or-next game per team
- Next Game first on Schedules
- Previous Games collapsed
- Cubs grouped by month
- compact My Teams
- week accordions for CFB, NFL, College Volleyball and Premier League
- one-at-a-time Standings selector
- tighter mobile spacing/tap targets

## Betting lines everywhere
DraftKings lines now render anywhere a game is listed and a market is available:
- Up Next
- My Teams next-game rows
- Schedules
- College Football
- NFL
- College Volleyball
- Premier League
- game detail

## Current DraftKings fix
The updater now uses DraftKings' v1 full event-group endpoint:
`/sites/<state>-SB/api/v1/eventgroup/<group>/full?format=json`

Known groups:
- MLB 84240
- NFL 88808
- College Football 87637

Illinois is tried first, then New Jersey, then generic.
EPL and college volleyball are discovered dynamically when DraftKings posts those markets.

Old DraftKings data is no longer preserved on a failed refresh.
The browser also refuses to display odds older than 50 minutes.

## Upload
Replace:
- index.html
- sports-data.json
- sports-data.js
- scripts/update_data.py

Then run:
Actions → Update Dayton Sports Data → Run workflow

That first manual run is important because this clean build intentionally ships without stale odds.
