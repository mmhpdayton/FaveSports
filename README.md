# Dayton Sports V13.3

Fixes the Cubs live score on Home / Upcoming & Where to Watch.

## What was wrong
The live Cubs updater was fetching the current MLB game correctly, but it was searching for generic `.game-card` / `.event-card` DOM elements. The actual Home card uses `.up-card`, and Home is frequently re-rendered by the site's normal score hydration.

## What changed
- The Cubs live event now writes directly into the underlying `D.upcoming` data.
- The actual Upcoming card renderer displays that live score.
- The Cubs Upcoming card receives the ESPN event ID and is clickable into the MLB game-detail view.
- The live SiriusXM Cubs button is rendered as part of the card itself.
- The Cubs live data is re-applied after normal Home score refreshes so it cannot be wiped out.
- Live Cubs polling remains every 30 seconds.

## Upgrade from V13.2
Replace:
- index.html
- sports-data.json
- sports-data.js

`scripts/update_data.py` from V13.2 is unchanged and can remain in place.
