# Dayton Sports V13.9

Switches betting-line architecture to DraftKings Sportsbook as the primary source.

## Primary DraftKings pages
- MLB: https://sportsbook.draftkings.com/leagues/baseball/mlb
- NFL: https://sportsbook.draftkings.com/leagues/football/nfl
- College Football: https://sportsbook.draftkings.com/leagues/football/ncaaf

DraftKings Network remains fallback-only if the Sportsbook page does not expose usable game lines during an updater run.

## College Volleyball
The updater now checks DraftKings' Volleyball / A-Z Sports navigation for a live NCAA / college women's-volleyball league page.

If DraftKings has college-volleyball markets posted:
- those games are ingested as `cvb`
- spread/handicap, moneyline and total are shown on College Volleyball game rows
- the same lines appear inside volleyball game-detail pages

If DraftKings does not have that league posted:
- no other sportsbook is substituted
- Dayton Sports shows "DraftKings Sportsbook — Lines not posted"

## Parsing strategy
The updater first parses embedded Sportsbook JSON for events/markets/outcomes.
If that is unavailable it tries server-rendered Sportsbook text.
Only after that does NFL/CFB/MLB fall back to DraftKings Network.

## Preserved from V13.8
- daily merged college-volleyball schedules
- weekly expand/collapse volleyball UX
- live scoring
- Amundsen Varsity
- Cubs live score and game detail
- SiriusXM priority team audio
- College Football All-FBS/conference views
- 30-minute GitHub workflow

## Upgrade from V13.8
Replace:
- index.html
- sports-data.json
- sports-data.js
- scripts/update_data.py

The existing V13.5 30-minute workflow is unchanged.
