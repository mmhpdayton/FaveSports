# Dayton Sports V12.1

Small patch over V12.

Changes:
- Wisconsin vs Kentucky on Aug. 21 is corrected to ESPN in the baseline data.
- ESPN Where to Watch is now the preferred broadcast source for public-team games in the next 21 days.
- The existing ESPN team schedule feed remains the fallback when Where to Watch cannot be matched cleanly.
- All V12 GitHub Actions automation remains unchanged.

If V12 is already uploaded, you only need to replace:
- sports-data.json
- sports-data.js
- scripts/update_data.py
- index.html (only for the V12.1 footer/version label)
