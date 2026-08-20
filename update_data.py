#!/usr/bin/env python3
"""
Dayton Sports automated data updater.

- Refreshes public-team schedules/results/broadcast metadata.
- Refreshes EPL/NFL/MLB standings.
- Refreshes AP / Coaches rankings when ESPN exposes a valid poll payload.
- Attempts AVCA women's volleyball rankings; preserves last-good data if unavailable.
- Regenerates Upcoming & Where to Watch.
- Never replaces a known-good dataset with an obviously incomplete response.

No secrets or third-party Python packages are required.
"""

from __future__ import annotations

import json
from html import unescape
import re
import sys
import urllib.request
import html as html_lib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "sports-data.json"
JS_PATH = ROOT / "sports-data.js"
CT = ZoneInfo("America/Chicago")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://sportsbook.draftkings.com/",
    "Origin": "https://sportsbook.draftkings.com",
}

TEAM_ALIASES = {
    "nd": ["notre dame", "fighting irish"],
    "wisc": ["wisconsin", "badgers"],
    "lfc": ["liverpool"],
    "gb": ["green bay", "packers"],
    "buf": ["buffalo", "bills"],
    "ind": ["indianapolis", "colts"],
    "cubs": ["chicago cubs", "cubs"],
}

SCHEDULES = {
    "nd": ("https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/87/schedule?season=2026", 10, 18),
    "wisc": ("https://site.api.espn.com/apis/site/v2/sports/volleyball/womens-college-volleyball/teams/275/schedule?season=2026", 20, 45),
    "lfc": ("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/364/schedule?season=2026", 30, 45),
    "gb": ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/gb/schedule?season=2026", 17, 25),
    "buf": ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/buf/schedule?season=2026", 17, 25),
    "ind": ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/ind/schedule?season=2026", 17, 25),
    "cubs": ("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/chc/schedule?season=2026&seasontype=2", 162, 162),
}

STANDINGS_URLS = {
    "epl": "https://site.api.espn.com/apis/v2/sports/soccer/eng.1/standings?season=2026",
    "nfl": "https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season=2026&type=0",
    "mlb": "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings?season=2026&type=0",
}

RANKING_URLS = {
    "cfb": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/rankings",
    "avca": "https://site.api.espn.com/apis/site/v2/sports/volleyball/womens-college-volleyball/rankings",
}


def fetch_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


WTW_NETWORKS = [
    "ESPN", "ESPN2", "ESPNU", "ESPN+", "ESPN Deportes", "ESPN Unlimited",
    "ABC", "FOX", "FS1", "FS2", "CBS", "CBS Sports Network", "NBC",
    "Peacock", "USA Network", "NFL Network", "Big Ten Network", "B1G+",
    "SEC Network", "ACC Network", "Marquee Sports Network",
    "Marquee Sports Net", "Apple TV", "Prime Video", "Paramount+",
    "MLB.TV", "Packers TV Network"
]


def wtw_date_code(game: dict) -> str | None:
    try:
        d = datetime.strptime(f"{game['date']} 2026", "%b %d %Y")
        return d.strftime("%Y%m%d")
    except Exception:
        return None


def clean_wtw_html(raw: str) -> str:
    # ESPN's Where-to-Watch page is server-rendered today, but this also
    # handles HTML entities and hidden markup if the page structure shifts.
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def find_wtw_network(page_text: str, our_aliases: list[str], opponent: str) -> str | None:
    """
    Match an event by both teams, then read the broadcast names immediately
    after that matchup. We deliberately prefer a single national/main network
    when present; otherwise we return the first clean recognized option.
    """
    page = norm(page_text)
    opp_tokens = [x for x in norm(opponent).split() if len(x) >= 4]

    # Locate a compact window containing one of our names and the opponent.
    positions = []
    for alias in our_aliases:
        p = page.find(norm(alias))
        while p >= 0:
            positions.append(p)
            p = page.find(norm(alias), p + 1)

    raw_lower = page_text.lower()
    for pos in positions:
        # norm() changes offsets, so use alias text to recover a raw-text window.
        alias = next((a for a in our_aliases if norm(a) in page[max(0,pos-30):pos+80]), our_aliases[0])
        raw_pos = raw_lower.find(alias.lower())
        if raw_pos < 0:
            continue
        window = page_text[max(0, raw_pos - 180): raw_pos + 700]
        nw = norm(window)
        if opp_tokens and not any(tok in nw for tok in opp_tokens):
            continue

        found = []
        for network in WTW_NETWORKS:
            if re.search(rf"(?<![A-Za-z0-9+]){re.escape(network)}(?![A-Za-z0-9+])", window, re.I):
                found.append(network)

        if not found:
            continue

        # Prefer the main ESPN network when ESPN is explicitly present,
        # but don't mistake ESPN2/ESPNU/ESPN+ for ESPN.
        if re.search(r"(?<![A-Za-z0-9+])ESPN(?![A-Za-z0-9+])", window, re.I):
            return "ESPN"

        # Remove duplicate aliases while preserving order.
        deduped = []
        for n in found:
            if n not in deduped:
                deduped.append(n)
        return " / ".join(deduped[:3])

    return None


def refresh_where_to_watch(data: dict):
    """
    ESPN Where to Watch is the preferred broadcast source for games in the
    next 21 days. Schedule-feed TV data remains the fallback.
    """
    today = datetime.now(CT).date()
    cutoff = today + timedelta(days=21)
    page_cache = {}

    for team in data.get("teams", []):
        tid = team.get("id")
        aliases = TEAM_ALIASES.get(tid)
        if not aliases:
            continue

        for game in team.get("schedule", []):
            d = game_date(game)
            if not d or d < today or d > cutoff or is_finished(game):
                continue

            code = wtw_date_code(game)
            if not code:
                continue

            if code not in page_cache:
                try:
                    raw = fetch_text(f"https://www.espn.com/where-to-watch/_/dates/{code}")
                    page_cache[code] = clean_wtw_html(raw)
                except Exception as exc:
                    print(f"where-to-watch {code}: unavailable ({exc})")
                    page_cache[code] = ""

            page_text = page_cache[code]
            if not page_text:
                continue

            network = find_wtw_network(page_text, aliases, game.get("opp", ""))
            if network:
                old = game.get("tv", "")
                game["tv"] = network
                if old != network:
                    print(f"where-to-watch {tid} {game.get('date')}: {old or 'TBD'} -> {network}")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def display_team(c: dict) -> str:
    t = c.get("team") or {}
    return t.get("displayName") or t.get("shortDisplayName") or t.get("name") or t.get("abbreviation") or ""


def matches_team(c: dict, aliases: list[str]) -> bool:
    n = norm(" ".join([
        display_team(c),
        (c.get("team") or {}).get("abbreviation", ""),
    ]))
    return any(norm(a) in n for a in aliases)


def chicago_datetime(iso: str):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CT)
    return d.strftime("%b %-d"), d.strftime("%-I:%M %p CT")


def extract_score(event: dict):
    comp = (event.get("competitions") or [{}])[0]
    cs = comp.get("competitors") or []
    if len(cs) < 2:
        return None
    home = next((x for x in cs if x.get("homeAway") == "home"), cs[0])
    away = next((x for x in cs if x.get("homeAway") == "away"), cs[1])
    st = ((event.get("status") or {}).get("type") or {})
    state = st.get("state")
    completed = bool(st.get("completed")) or state == "post"
    live = state == "in"
    if not completed and not live:
        return None

    def number(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    hs, as_ = number(home.get("score")), number(away.get("score"))
    return {
        "homeName": display_team(home),
        "awayName": display_team(away),
        "homeScore": str(home.get("score", "")),
        "awayScore": str(away.get("score", "")),
        "homeWinner": completed and hs > as_,
        "awayWinner": completed and as_ > hs,
        "live": live,
    }


def event_to_game(event: dict, team_id: str):
    comp = (event.get("competitions") or [{}])[0]
    cs = comp.get("competitors") or []
    ours = next((x for x in cs if matches_team(x, TEAM_ALIASES[team_id])), None)
    opp = next((x for x in cs if x is not ours), None)
    if not ours or not opp or not event.get("date"):
        return None

    date, time = chicago_datetime(event["date"])
    broadcasts = []
    for b in comp.get("broadcasts") or []:
        broadcasts.extend(b.get("names") or [])

    notes = " · ".join(
        x.get("headline") or x.get("type") or ""
        for x in (comp.get("notes") or [])
        if (x.get("headline") or x.get("type"))
    )
    season_name = (
        (event.get("seasonType") or {}).get("name")
        or (event.get("seasonType") or {}).get("slug")
        or ""
    )

    g = {
        "date": date,
        "time": time,
        "opp": display_team(opp),
        "ha": "AWAY" if ours.get("homeAway") == "away" else ("HOME" if ours.get("homeAway") == "home" else "NEUTRAL"),
    }
    venue = (comp.get("venue") or {}).get("fullName")
    if venue:
        g["venue"] = venue
    if broadcasts:
        g["tv"] = " / ".join(dict.fromkeys(broadcasts))
    if notes or season_name:
        g["event"] = notes or season_name

    if team_id in {"gb", "buf", "ind"}:
        text = norm((season_name or "") + " " + (notes or ""))
        g["type"] = "PRESEASON" if "preseason" in text else "REGULAR"

    score = extract_score(event)
    if score:
        g["_score"] = score
        if not score["live"]:
            our_is_home = g["ha"] == "HOME"
            our_score = float(score["homeScore"] if our_is_home else score["awayScore"])
            their_score = float(score["awayScore"] if our_is_home else score["homeScore"])
            result_letter = "W" if our_score > their_score else ("L" if our_score < their_score else "T")
            def tidy(n):
                return str(int(n)) if float(n).is_integer() else str(n)
            g["result"] = f"{result_letter} {tidy(our_score)}–{tidy(their_score)}"

    return g


def refresh_schedules(data: dict):
    team_by_id = {t["id"]: t for t in data.get("teams", [])}
    for team_id, (url, min_games, max_games) in SCHEDULES.items():
        try:
            payload = fetch_json(url)
            games = [event_to_game(e, team_id) for e in payload.get("events", [])]
            games = [g for g in games if g]
            # Liverpool should remain the Premier League schedule, not cup/friendly clutter.
            if team_id == "lfc":
                games = [g for g in games if not re.search(r"cup|champions|friendly", g.get("event", ""), re.I)]
            if min_games <= len(games) <= max_games:
                team_by_id[team_id]["schedule"] = games
                print(f"schedule {team_id}: {len(games)} games")
            else:
                print(f"schedule {team_id}: rejected incomplete/unexpected count {len(games)}")
        except Exception as exc:
            print(f"schedule {team_id}: preserved last-good data ({exc})")


def walk_groups(node, out=None):
    if out is None:
        out = []
    if not isinstance(node, dict):
        return out
    st = node.get("standings") or {}
    if isinstance(st.get("entries"), list):
        out.append({"name": node.get("name") or node.get("abbreviation") or node.get("shortName") or "", "entries": st["entries"]})
    for key in ("children", "groups"):
        for child in node.get(key) or []:
            walk_groups(child, out)
    return out


def compact_entries(entries: list[dict]):
    # Preserve exactly what the front end needs, not the entire ESPN payload.
    clean = []
    for e in entries:
        t = e.get("team") or {}
        clean.append({
            "team": {
                "displayName": t.get("displayName") or t.get("shortDisplayName") or t.get("name"),
                "shortDisplayName": t.get("shortDisplayName"),
                "name": t.get("name"),
                "logo": ((t.get("logos") or [{}])[0]).get("href") if t.get("logos") else t.get("logo"),
            },
            "stats": [
                {
                    "name": s.get("name"),
                    "abbreviation": s.get("abbreviation"),
                    "shortDisplayName": s.get("shortDisplayName"),
                    "displayValue": s.get("displayValue"),
                    "value": s.get("value"),
                }
                for s in (e.get("stats") or [])
            ],
        })
    return clean


def find_group(groups, wanted: str):
    w = norm(wanted)
    return next((g for g in groups if w in norm(g.get("name", ""))), None)


def refresh_standings(data: dict):
    stored = data.setdefault("standings", {})

    # Premier League
    try:
        payload = fetch_json(STANDINGS_URLS["epl"])
        groups = walk_groups(payload)
        best = max(groups, key=lambda g: len(g["entries"]), default=None)
        if best and len(best["entries"]) >= 18:
            stored["epl"] = compact_entries(best["entries"])
            print("standings EPL: updated")
    except Exception as exc:
        print(f"standings EPL: preserved ({exc})")

    # NFL divisions
    try:
        payload = fetch_json(STANDINGS_URLS["nfl"])
        groups = walk_groups(payload)
        mapping = {"nfcNorth": "NFC North", "afcEast": "AFC East", "afcSouth": "AFC South"}
        for key, name in mapping.items():
            g = find_group(groups, name)
            if g and len(g["entries"]) == 4:
                stored[key] = compact_entries(g["entries"])
                print(f"standings {name}: updated")
    except Exception as exc:
        print(f"standings NFL: preserved ({exc})")

    # MLB NL Central
    try:
        payload = fetch_json(STANDINGS_URLS["mlb"])
        groups = walk_groups(payload)
        g = find_group(groups, "NL Central")
        if g and len(g["entries"]) == 5:
            stored["nlCentral"] = compact_entries(g["entries"])
            print("standings NL Central: updated")
    except Exception as exc:
        print(f"standings MLB: preserved ({exc})")


def ranking_name(poll: dict) -> str:
    return norm(poll.get("name") or poll.get("shortName") or poll.get("headline") or "")


def parse_poll(poll: dict):
    rows = poll.get("ranks") or poll.get("rankings") or []
    parsed = []
    fpv = {}
    for row in rows:
        team = row.get("team") or {}
        name = team.get("displayName") or team.get("shortDisplayName") or row.get("teamName")
        rank = row.get("current") or row.get("rank") or row.get("ranking")
        if not name or rank is None:
            continue
        try:
            rank = int(rank)
        except Exception:
            continue
        parsed.append((rank, name))
        votes = row.get("firstPlaceVotes")
        if votes not in (None, "", 0, "0"):
            try:
                fpv[name] = int(votes)
            except Exception:
                pass
    parsed.sort()
    return [name for _, name in parsed[:25]], fpv


def refresh_rankings(data: dict):
    rankings = data.setdefault("rankings", {})
    fpv_all = rankings.setdefault("firstPlaceVotes", {})

    try:
        payload = fetch_json(RANKING_URLS["cfb"])
        polls = payload.get("rankings") or payload.get("polls") or []
        for poll in polls:
            n = ranking_name(poll)
            teams, fpv = parse_poll(poll)
            if len(teams) < 25:
                continue
            if "associated press" in n or re.search(r"\bap\b", n):
                rankings["ap"] = teams
                if fpv:
                    fpv_all["ap"] = fpv
                print("rankings AP: updated")
            elif "coach" in n:
                rankings["coaches"] = teams
                if fpv:
                    fpv_all["coaches"] = fpv
                print("rankings Coaches: updated")
    except Exception as exc:
        print(f"rankings football: preserved ({exc})")

    try:
        payload = fetch_json(RANKING_URLS["avca"])
        polls = payload.get("rankings") or payload.get("polls") or []
        candidates = []
        for poll in polls:
            teams, _ = parse_poll(poll)
            if len(teams) >= 25:
                candidates.append((ranking_name(poll), teams))
        if candidates:
            best = next((t for n, t in candidates if "avca" in n), candidates[0][1])
            rankings["avca"] = best
            print("rankings AVCA: updated")
    except Exception as exc:
        print(f"rankings AVCA: preserved ({exc})")


def game_date(game: dict):
    try:
        return datetime.strptime(f"{game['date']} 2026", "%b %d %Y").date()
    except Exception:
        return None


def is_finished(game: dict):
    s = game.get("_score")
    return bool((s and not s.get("live")) or re.match(r"^(W|L|T|FINAL)\b", game.get("result", ""), re.I))


def update_team_contexts(data: dict):
    rankings = data.get("rankings", {})
    teams = {t["id"]: t for t in data.get("teams", [])}
    try:
        ap = rankings.get("ap", []).index("Notre Dame") + 1
    except ValueError:
        ap = None
    try:
        coaches = rankings.get("coaches", []).index("Notre Dame") + 1
    except ValueError:
        coaches = None
    if "nd" in teams and (ap or coaches):
        pieces = []
        if ap:
            pieces.append(f"#{ap} AP")
        if coaches:
            pieces.append(f"#{coaches} Coaches")
        teams["nd"]["context"] = " · ".join(pieces)

    try:
        avca = rankings.get("avca", []).index("Wisconsin") + 1
        teams["wisc"]["context"] = f"#{avca} AVCA"
    except (ValueError, KeyError):
        pass


def regenerate_upcoming(data: dict):
    today = datetime.now(CT).date()
    horizon = today + timedelta(days=7)
    teams = {t["id"]: t for t in data.get("teams", [])}
    featured_order = ["payton", "amundsen", "amundsenvarsity", "nd", "wisc", "lfc", "gb", "buf", "cubs"]

    chosen = []
    chosen_keys = set()

    def eligible(tid, g):
        d = game_date(g)
        if not d or d < today or is_finished(g):
            return False
        if tid in {"gb", "buf"} and g.get("type") == "PRESEASON":
            return False
        return True

    def key(tid, g):
        return (tid, g.get("date"), g.get("opp"))

    # Guarantee one next game per featured favorite.
    for tid in featured_order:
        t = teams.get(tid)
        if not t:
            continue
        nxt = next((g for g in t.get("schedule", []) if eligible(tid, g)), None)
        if nxt:
            chosen.append((game_date(nxt), tid, nxt))
            chosen_keys.add(key(tid, nxt))

    # Then add other games in the next seven days.
    extras = []
    for tid in featured_order:
        t = teams.get(tid)
        if not t:
            continue
        for g in t.get("schedule", []):
            d = game_date(g)
            if not d or d < today or d > horizon or not eligible(tid, g):
                continue
            k = key(tid, g)
            if k not in chosen_keys:
                extras.append((d, tid, g))
                chosen_keys.add(k)

    chosen.extend(extras)
    chosen.sort(key=lambda x: x[0])

    data["upcoming"] = [{
        "id": tid,
        "date": d.strftime("%a · %b %d").upper(),
        "opp": ("@ " if g.get("ha") == "AWAY" else "vs ") + g.get("opp", ""),
        "time": g.get("time", ""),
        "tv": g.get("tv", ""),
        "where": g.get("ha", ""),
    } for d, tid, g in chosen[:14]]


SXM_PRIORITY = {
    "cubs": {
        "team_names": ["Chicago Cubs", "Cubs"],
        "page": "https://www.siriusxm.com/sports/mlb/chicago-cubs",
        "sport": "mlb",
    },
    "nd": {
        "team_names": ["Notre Dame", "Fighting Irish"],
        "page": "https://www.siriusxm.com/sports/ncaaf/notre-dame",
        "sport": "ncaaf",
    },
    "gb": {
        "team_names": ["Green Bay Packers", "Packers"],
        "page": "https://www.siriusxm.com/sports/nfl/green-bay-packers",
        "sport": "nfl",
    },
}

def sxm_channel_url(channel):
    """Map SiriusXM sports play-by-play channel numbers to stable channel pages."""
    try:
        ch = int(channel)
    except Exception:
        return None

    # MLB play-by-play channel pages are named mlb-play-by-play-NNN.
    if 175 <= ch <= 184:
        return f"https://www.siriusxm.com/channels/mlb-play-by-play-{ch}"

    # NFL play-by-play channel pages are named nfl-play-by-play-NNN.
    if 225 <= ch <= 234 or 380 <= ch <= 383:
        return f"https://www.siriusxm.com/channels/nfl-play-by-play-{ch}"

    # Some app-only / team feeds use 800+ channels and not every one has a
    # predictable public slug. Fall back to the team page instead of guessing.
    return None

def strip_html_text(raw):
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()

def find_priority_sxm_channel(team_key, raw_html):
    cfg = SXM_PRIORITY[team_key]
    text = strip_html_text(raw_html)

    # SiriusXM team pages commonly present:
    # Team ... Home/Away • CH 184 ... and a second app channel.
    # We look near the team-name occurrence and prefer the first normal
    # satellite/play-by-play channel (sub-400) rather than app-only 800+.
    matches = []
    low = text.lower()
    for team_name in cfg["team_names"]:
        start = 0
        needle = team_name.lower()
        while True:
            i = low.find(needle, start)
            if i < 0:
                break
            window = text[max(0, i-250): i+650]
            for m in re.finditer(r"\bCH(?:ANNEL)?\.?\s*(\d{2,3})\b", window, flags=re.I):
                ch = int(m.group(1))
                distance = abs((max(0, i-250) + m.start()) - i)
                matches.append((distance, ch))
            start = i + len(needle)

    if not matches:
        return None

    # Prefer ordinary car/play-by-play channels over app-only 800+ feeds.
    normal = [(d,ch) for d,ch in matches if ch < 400]
    chosen = min(normal or matches, key=lambda x: x[0])[1]
    return chosen

def refresh_siriusxm(data):
    sxm = data.setdefault("siriusxm", {})
    for key, cfg in SXM_PRIORITY.items():
        try:
            raw = fetch_text(cfg["page"])
            ch = find_priority_sxm_channel(key, raw)
            entry = {
                "team": key,
                "page": cfg["page"],
                "channel": ch,
                "channelUrl": sxm_channel_url(ch) if ch else None,
            }
            # Keep the team page as a safe fallback when exact channel mapping
            # is unavailable or the game/channel has not yet been posted.
            entry["listenUrl"] = entry["channelUrl"] or cfg["page"]
            sxm[key] = entry
        except Exception as exc:
            print(f"SiriusXM refresh failed for {key}: {exc}")



# Official DraftKings Network odds pages. These pages publish DraftKings
# Sportsbook moneyline / spread (run line for MLB) / total prices without
# requiring a sportsbook login or geolocation session.

# DraftKings Sportsbook game lines.
# These event-group IDs are the league IDs used by DraftKings' own Sportsbook feed.
DK_EVENTGROUP_IDS = {
    "mlb": "84240",
    "nfl": "88808",
    "cfb": "87637",
}

DK_API_TEMPLATES = [
    "https://sportsbook.draftkings.com/sites/US-IL-SB/api/v1/eventgroup/{group}/full?format=json",
    "https://sportsbook.draftkings.com/sites/US-NJ-SB/api/v1/eventgroup/{group}/full?format=json",
    "https://sportsbook.draftkings.com/sites/US-SB/api/v1/eventgroup/{group}/full?format=json",
]

DK_EPL_DISCOVERY = [
    "https://sportsbook.draftkings.com/leagues/soccer/english-premier-league",
    "https://sportsbook.draftkings.com/sports/soccer",
]

DK_VOLLEYBALL_DISCOVERY = [
    "https://sportsbook.draftkings.com/sports/volleyball",
    "https://sportsbook.draftkings.com/",
]

def dk_clean_odds(v):
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("american") or v.get("americanOdds") or v.get("display")
    if v is None:
        return None
    s = str(v).replace("−","-").replace("–","-").strip()
    # DraftKings sometimes emits EV/Even.
    if s.lower() in {"ev","even","even money"}:
        return "+100"
    return s

def dk_clean_team(v):
    v = html_lib.unescape(str(v or ""))
    return re.sub(r"\s+"," ",v).strip(" -·|")

def dk_event_teams(event):
    away = event.get("teamName1") or event.get("awayTeamName")
    home = event.get("teamName2") or event.get("homeTeamName")
    parts = event.get("participants") or []
    for p in parts:
        if not isinstance(p, dict):
            continue
        role = str(p.get("venueRole") or p.get("homeAway") or p.get("role") or "").lower()
        name = p.get("name") or p.get("displayName") or p.get("teamName")
        if role in {"away","visitor"} and name:
            away = name
        elif role == "home" and name:
            home = name
    if (not away or not home) and event.get("name"):
        bits = re.split(r"\s+@\s+|\s+vs\.?\s+", str(event["name"]), flags=re.I)
        if len(bits) == 2:
            away = away or bits[0]
            home = home or bits[1]
    return dk_clean_team(away), dk_clean_team(home)

def dk_outcome_name(o):
    return dk_clean_team(
        o.get("participant") or o.get("label") or o.get("name") or
        o.get("participantName") or o.get("displayName")
    )

def dk_outcome_line(o):
    v = o.get("line")
    if v is None: v = o.get("points")
    if v is None: v = o.get("handicap")
    return None if v is None else str(v).replace("−","-").replace("–","-")

def dk_outcome_price(o):
    for key in ("oddsAmerican","americanOdds","odds","price"):
        if key in o:
            return dk_clean_odds(o[key])
    return None

def dk_iter_offers(event_group):
    """Yield every offer object under all categories/subcategories."""
    for cat in event_group.get("offerCategories") or []:
        cat_name = str(cat.get("name") or "")
        for desc in cat.get("offerSubcategoryDescriptors") or []:
            sub_name = str(desc.get("name") or "")
            sub = desc.get("offerSubcategory") or {}
            groups = sub.get("offers") or []
            for offer_group in groups:
                seq = offer_group if isinstance(offer_group, list) else [offer_group]
                for offer in seq:
                    if isinstance(offer, dict):
                        yield cat_name, sub_name, offer

def dk_market_type(cat_name, sub_name, offer):
    text = " ".join([
        cat_name, sub_name,
        str(offer.get("label") or ""),
        str(offer.get("name") or ""),
        str(offer.get("marketName") or ""),
    ]).lower()
    if "moneyline" in text or "money line" in text:
        return "moneyline"
    if "run line" in text or "spread" in text or "handicap" in text:
        return "spread"
    if "total" in text or "over/under" in text or "over under" in text:
        return "total"
    return None

def dk_parse_eventgroup(payload, sport):
    eg = payload.get("eventGroup") or payload
    events = eg.get("events") or payload.get("events") or []
    event_map = {}
    games = {}

    for e in events:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("eventId") or e.get("id") or "")
        if not eid:
            continue
        away, home = dk_event_teams(e)
        event_map[eid] = e
        games[eid] = {
            "sport": sport,
            "eventId": eid,
            "away": away,
            "home": home,
            "startDate": e.get("startDate") or e.get("startDateTime"),
            "moneyline": {},
            "spread": {},
            "total": {},
            "source": "DraftKings Sportsbook",
        }

    for cat_name, sub_name, offer in dk_iter_offers(eg):
        market = dk_market_type(cat_name, sub_name, offer)
        if not market:
            continue

        eid = str(
            offer.get("eventId") or offer.get("providerEventId") or
            offer.get("eventID") or ""
        )
        if not eid:
            continue

        rec = games.setdefault(eid, {
            "sport": sport, "eventId": eid, "away": "", "home": "",
            "moneyline": {}, "spread": {}, "total": {},
            "source": "DraftKings Sportsbook",
        })

        # If the event wasn't in events[], recover matchup identity from offer.
        if not rec.get("away") or not rec.get("home"):
            ev = event_map.get(eid, {})
            away, home = dk_event_teams(ev)
            rec["away"] = rec.get("away") or away
            rec["home"] = rec.get("home") or home

        outcomes = offer.get("outcomes") or []
        if market == "moneyline":
            for o in outcomes:
                if not isinstance(o, dict): continue
                name, price = dk_outcome_name(o), dk_outcome_price(o)
                if name and price:
                    rec["moneyline"][name] = price

        elif market == "spread":
            for o in outcomes:
                if not isinstance(o, dict): continue
                name, line, price = dk_outcome_name(o), dk_outcome_line(o), dk_outcome_price(o)
                if name and (line is not None or price):
                    rec["spread"][name] = {"line": line, "odds": price}

        elif market == "total":
            for o in outcomes:
                if not isinstance(o, dict): continue
                name = dk_outcome_name(o).lower()
                line, price = dk_outcome_line(o), dk_outcome_price(o)
                # Some DK payloads store "Over"/"Under" as label rather than participant.
                label = str(o.get("label") or o.get("name") or o.get("participant") or "").lower()
                side = name or label
                if "over" in side:
                    if line is not None: rec["total"]["line"] = line
                    rec["total"]["overOdds"] = price
                elif "under" in side:
                    if line is not None: rec["total"].setdefault("line", line)
                    rec["total"]["underOdds"] = price

    out = []
    for g in games.values():
        if not g.get("away") or not g.get("home"):
            continue
        if g["moneyline"] or g["spread"] or g["total"]:
            out.append(g)
    return out

def dk_fetch_eventgroup(sport, group):
    last_exc = None
    for tmpl in DK_API_TEMPLATES:
        url = tmpl.format(group=group)
        try:
            payload = fetch_json(url, timeout=20)
            games = dk_parse_eventgroup(payload, sport)
            if games:
                return games, url
        except Exception as exc:
            last_exc = exc
            print(f"DraftKings eventgroup failed {sport} via {url}: {exc}")
    if last_exc:
        raise last_exc
    return [], None

def dk_plain_text(raw):
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<[^>]+>", "\n", raw)
    raw = html_lib.unescape(raw)
    return "\n".join(re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip())

def dk_discover_group_from_pages(pages, required_terms):
    for page in pages:
        try:
            raw = fetch_text(page)
        except Exception:
            continue
        low = raw.lower()
        for pat in (
            r'eventgroup/(\d{3,10})',
            r'eventgroup(?:id)?["\':=\s]+(\d{3,10})',
            r'13l(\d{3,10})q',
        ):
            for m in re.finditer(pat, low, flags=re.I):
                window = low[max(0,m.start()-600):min(len(low),m.end()+600)]
                if all(term.lower() in window for term in required_terms):
                    return m.group(1)
    return None

def dk_discover_epl_group():
    return dk_discover_group_from_pages(DK_EPL_DISCOVERY, ["premier"])

def dk_discover_college_volleyball_group():
    return dk_discover_group_from_pages(DK_VOLLEYBALL_DISCOVERY, ["volleyball"])


def refresh_draftkings_odds(data):
    all_games = []
    source_pages = {}
    errors = {}
    seen = set()

    groups = dict(DK_EVENTGROUP_IDS)
    epl_group = dk_discover_epl_group()
    if epl_group:
        groups["epl"] = epl_group
    cvb_group = dk_discover_college_volleyball_group()
    if cvb_group:
        groups["cvb"] = cvb_group

    for sport, group in groups.items():
        try:
            games, source_url = dk_fetch_eventgroup(sport, group)
            if source_url:
                source_pages[sport] = source_url
            for g in games:
                key = (sport, dk_clean_team(g.get("away")).lower(), dk_clean_team(g.get("home")).lower(), str(g.get("startDate") or "")[:10])
                if key in seen:
                    continue
                seen.add(key)
                all_games.append(g)
        except Exception as exc:
            errors[sport] = str(exc)
            print(f"DraftKings {sport}: current feed unavailable ({exc})")

    # Never preserve an old odds snapshot as if it were current.
    data["draftkingsOdds"] = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "DraftKings",
        "primarySource": "DraftKings Sportsbook v1 event-group feed",
        "sourcePages": source_pages,
        "errors": errors,
        "eplDiscovered": bool(epl_group),
        "collegeVolleyballDiscovered": bool(cvb_group),
        "games": all_games,
        "status": "ok" if all_games else "unavailable",
    }

    counts = {}
    for g in all_games:
        counts[g["sport"]] = counts.get(g["sport"], 0) + 1
    print(f"DraftKings current odds refresh: {counts or 'no current lines returned'}")


def main():
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    refresh_schedules(data)
    refresh_where_to_watch(data)
    refresh_standings(data)
    refresh_rankings(data)
    update_team_contexts(data)
    refresh_siriusxm(data)
    refresh_draftkings_odds(data)
    regenerate_upcoming(data)

    data["version"] = "v14.0"
    data["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("automation", {})["enabled"] = True
    data["automation"]["lastRun"] = data["lastUpdated"]

    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    JS_PATH.write_text("window.FAVE_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("Dayton Sports data refresh complete.")


if __name__ == "__main__":
    main()
