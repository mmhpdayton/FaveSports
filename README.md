# Dayton Sports V13.0

Cubs live-game fix.

## Cubs live behavior
- Dayton Sports now fetches the current day's MLB scoreboard directly in the browser.
- If the Cubs are playing, the Cubs card is patched with the live/final score and game status.
- Cubs live data refreshes every 30 seconds while the site is open.
- The Cubs game card becomes clickable and opens the same in-app game detail experience used for NFL, college football, and Premier League.

## MLB game detail
The in-app Cubs game page supports:
- live score/status
- TV / stream
- venue
- attendance when available
- baseball linescore by inning
- key stats when supplied
- scoring plays when supplied
- 30-second refresh while the detail page is open

## Why this was needed
The league tabs had the newer live-score engine, but the Home/Upcoming Cubs card was still relying on the older generated team data. A live Cubs game therefore exposed stale data and had no game-detail event ID.

## Upgrade from V12.9
Replace:
- index.html
- sports-data.json
- sports-data.js
