# Dayton Sports V12.9

Fixes the College Football submenu data source.

## Correct behavior
- Top 25: ranked-game view + Notre Dame
- All FBS: ESPN FBS group feed
- ACC: conference group feed
- B1G: conference group feed
- Big 12: conference group feed
- SEC: conference group feed
- AAC: conference group feed
- C-USA: conference group feed
- MAC: conference group feed
- Mountain West: conference group feed
- Sun Belt: conference group feed
- Pac-12: conference group feed

The previous version changed the display filter but still fetched ESPN's default ranked slate, which is why All FBS and conference views only showed ranked-team games.

## Preserved
- Top 25 always defaults when College Football is opened
- Week 0 handling
- TBD/flexible-date handling
- 60-second live scoring
- game-detail pages
- NFL and Premier League tabs

## Upgrade from V12.8
Replace:
- index.html
- sports-data.json
- sports-data.js
