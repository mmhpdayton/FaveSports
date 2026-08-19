# Dayton Sports V12.7

College Football browsing upgrade.

## New College Football submenu
The College Football schedule can now be filtered by:
- Top 25 — always the default, with Notre Dame included/highlighted
- All FBS
- ACC
- B1G
- Big 12
- SEC
- AAC
- C-USA
- MAC
- Mountain West
- Sun Belt
- Pac-12

The selected filter applies to every weekly accordion:
- current week expanded
- previous weeks collapsed with results
- future weeks collapsed

Whenever the user leaves and comes back to College Football, the view resets to Top 25.

## Data behavior
- College football scoreboard requests now use a large limit so All FBS can retrieve the full weekly slate.
- Week 0 still uses the Aug. 27–30 date window.
- Conference filtering uses ESPN conference metadata on the participating teams.
- Existing 60-second live scoring remains intact for every filter.
- V12.6 flexible/TBD date handling remains intact.

## Upgrade from V12.6
Replace:
- index.html
- sports-data.json
- sports-data.js

No Python updater or GitHub Actions change is required.
