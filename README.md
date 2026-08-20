# Dayton Sports V14.2.2 — Home Schedule Link Fix

Includes all V14.2.2 personalization:
- Payton JV Volleyball: Hadley - Setter
- Amundsen JV Football: Patrick - WR/DB
- Amundsen Varsity Football: Patrick dresses varsity

## Fix
Home-page "Go to Schedule" / team rows now use delegated click handling.

Because the compact My Teams rows are rendered dynamically, the old direct click handlers did not attach to them. Clicking a Home team row now:
1. opens Schedules
2. selects the correct team
3. renders that team's schedule immediately

## Upgrade
Replace:
- index.html

The sports-data files from V14.2.2 are unchanged, but the full ZIP includes them for convenience.
