# Dayton Sports V14.0

Three fixes requested Aug 20, 2026.

## 1. Top menu
Exact order:
1. Home
2. Schedules
3. College Football
4. Premier League
5. NFL
6. College Volleyball
7. Standings

Rankings remains available inside the app where team/ranking links point to it, but is no longer a top-level menu item.

## 2. Upcoming & Where to Watch
Upcoming is no longer dependent solely on the last GitHub-generated `sports-data.js`.

On every site load, after current schedules/results are hydrated from ESPN, the browser rebuilds Upcoming:
- removes prior-date games
- removes completed games
- guarantees the next eligible game for each featured team
- adds extra games within the next seven days
- excludes Packers/Bills preseason from Home Upcoming
- keeps Colts excluded
- preserves live score/event/game-detail data

This specifically prevents a completed Cubs game from yesterday remaining on Home if the updater has not yet refreshed the static file.

## 3. DraftKings betting lines
V13.9 parsed the visible Sportsbook page, which is not where the actual game-line data lives.

V14.0 uses DraftKings Sportsbook's event-group JSON feed:
- MLB event group: 84240
- NFL event group: 88808
- College Football event group: 87637

The updater searches all offer categories/subcategories and extracts:
- Point Spread / MLB Run Line
- Moneyline
- Over/Under

It tries the generic DraftKings Sportsbook endpoint first and Illinois / nash mirrors as fallbacks.

College Volleyball still uses discovery because the NCAA women's volleyball event-group ID can appear/disappear as DraftKings posts that market.

## Update frequency
The existing GitHub Action remains every 30 minutes.

## Fresh upload from V13.9
Replace:
- index.html
- sports-data.json
- sports-data.js
- scripts/update_data.py

The workflow file is unchanged from V13.5/V13.9.
