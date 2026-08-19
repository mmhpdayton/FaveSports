# Dayton Sports V13.2

Priority-team one-tap SiriusXM audio.

## Priority teams
- Chicago Cubs
- Notre Dame
- Green Bay Packers

## What changed
The GitHub Actions updater now checks each priority team's official SiriusXM page and attempts to capture the current published team-feed channel.

When an exact channel is available, Dayton Sports shows:
- 🎧 Cubs Radio · CH ###
- 🎧 Notre Dame Radio · CH ###
- 🎧 Packers Radio · CH ###

The link targets the corresponding SiriusXM channel page when Dayton Sports can map that channel to a stable SiriusXM live-channel URL.

If the exact channel has not yet been published, the button remains available and falls back to the official SiriusXM team page rather than disappearing.

## Mobile behavior
The link uses SiriusXM's normal HTTPS channel/team URLs. On a phone, SiriusXM/iOS/Android controls whether that URL hands off to the installed SiriusXM app or opens the mobile player. Dayton Sports does not use an undocumented custom-app URI scheme.

## Refresh cadence
The exact SiriusXM channel assignment is refreshed by the existing GitHub Action every 3 hours and on manual workflow runs.

## Upgrade from V13.1
Replace:
- index.html
- sports-data.json
- sports-data.js
- scripts/update_data.py

Existing `.github/workflows/update-data.yml` can remain unchanged.
