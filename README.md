# Dayton Sports V14.2.1

Fixes two College Volleyball regressions.

## College Volleyball league page
The ESPN women's-college-volleyball scoreboard does not behave consistently with a single `groups=` value.

V14.2.1 now merges three daily sources:
1. the unfiltered ESPN volleyball scoreboard
2. the selected conference / D-I group feed
3. `groups=50` as an additional fallback

It does this separately for all seven days in each displayed week, merges the results, and deduplicates by ESPN event ID.

This prevents one empty/broken group response from blanking an entire week.

## Wisconsin rankings in Schedules
The UI now reapplies the stored AVCA Top 25 at render time.

That means even if the live ESPN schedule refresh replaces:
`#3 Kentucky`
with:
`Kentucky`

Dayton Sports renders:
`#3 Kentucky`

The ranking restoration is applied to:
- Wisconsin Schedule cards
- Wisconsin Next Game hero
- Wisconsin compact My Teams row
- Wisconsin Up Next card

Exhibitions/alumni/tournament labels are left alone.

## Upgrade
Replace:
- index.html
- sports-data.json
- sports-data.js

Updater/workflow are unchanged from the V14.2 REDO.
