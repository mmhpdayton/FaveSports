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
    "User-Agent": "DaytonSports/13.9 (+GitHub Actions)",
    "Accept": "application/json,text/plain,*/*",
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

# DraftKings Sportsbook is the primary odds source.
# DraftKings Network remains a last-good fallback only.
DK_SPORTSBOOK_SOURCES = {
    "mlb": ["https://sportsbook.draftkings.com/leagues/baseball/mlb"],
    "nfl": [
        "https://sportsbook.draftkings.com/leagues/football/nfl",
        "https://sportsbook.draftkings.com/leagues/football/nfl-preseason",
    ],
    "cfb": ["https://sportsbook.draftkings.com/leagues/football/ncaaf"],
}

DK_NETWORK_FALLBACKS = {
    "mlb": ["https://dknetwork.draftkings.com/moneyline-total-spread/?tb_eg=MLB&tb_edate=n7days"],
    "nfl": ["https://dknetwork.draftkings.com/moneyline-total-spread/?tb_eg=NFL&tb_edate=n30days"],
    "cfb": ["https://dknetwork.draftkings.com/moneyline-total-spread/?tb_eg=College%20Football&tb_edate=n30days"],
}

DK_VOLLEYBALL_DISCOVERY = [
    "https://sportsbook.draftkings.com/sports/volleyball",
    "https://sportsbook.draftkings.com/",
]

def dk_clean_odds(v):
    if v is None:
        return None
    return str(v).replace("−", "-").replace("–", "-").strip()

def dk_clean_team(v):
    v = html_lib.unescape(str(v or ""))
    return re.sub(r"\s+", " ", v).strip(" -·|")

def dk_plain_text(raw):
    raw = re.sub(r"</(?:h[1-6]|div|p|li|tr|section|article|td|th|button|span)>", "\n", raw, flags=re.I)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html_lib.unescape(raw).replace("\u2212","-").replace("\xa0"," ")
    lines = [re.sub(r"\s+"," ",x).strip() for x in raw.splitlines()]
    return "\n".join(x for x in lines if x)

def dk_extract_json_blobs(raw):
    """Yield JSON blobs embedded in Sportsbook HTML."""
    blobs = []
    patterns = [
        r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    ]
    for pat in patterns:
        for m in re.finditer(pat, raw, flags=re.I|re.S):
            txt = html_lib.unescape(m.group(1)).strip()
            try:
                blobs.append(json.loads(txt))
            except Exception:
                pass
    return blobs

def dk_walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from dk_walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from dk_walk(v)

def dk_first(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None

def dk_parse_sportsbook_json(raw, sport):
    """
    Generic DraftKings Sportsbook embedded-JSON parser.
    Handles common event/market/outcome shapes without depending on one private API schema.
    """
    games_by_id = {}
    for blob in dk_extract_json_blobs(raw):
        for d in dk_walk(blob):
            # Capture event/team identity.
            event_id = dk_first(d, ["eventId","eventID","id"])
            name = dk_first(d, ["name","eventName","displayName"])
            participants = dk_first(d, ["participants","competitors","teams"])
            if event_id and (participants or (isinstance(name,str) and ("@" in name or " vs " in name.lower()))):
                rec = games_by_id.setdefault(str(event_id), {
                    "sport": sport, "eventId": str(event_id),
                    "away": None, "home": None,
                    "moneyline": {}, "spread": {}, "total": {},
                    "source": "DraftKings Sportsbook"
                })
                if isinstance(participants, list):
                    for p in participants:
                        if not isinstance(p, dict): continue
                        nm = dk_first(p, ["name","displayName","teamName"])
                        role = str(dk_first(p, ["venueRole","homeAway","role"]) or "").lower()
                        if nm:
                            if role in ("away","visitor"): rec["away"] = dk_clean_team(nm)
                            elif role == "home": rec["home"] = dk_clean_team(nm)
                if (not rec["away"] or not rec["home"]) and isinstance(name,str):
                    parts = re.split(r"\s+@\s+|\s+vs\.?\s+", name, flags=re.I)
                    if len(parts) == 2:
                        rec["away"], rec["home"] = map(dk_clean_team, parts)

            # Capture markets/outcomes; attach by event id when present.
            market_name = str(dk_first(d, ["marketName","name","label","displayName"]) or "")
            outcomes = dk_first(d, ["outcomes","selections","offers"])
            parent_event = dk_first(d, ["eventId","eventID","event"])
            if isinstance(parent_event, dict):
                parent_event = dk_first(parent_event, ["id","eventId"])
            if not parent_event or not isinstance(outcomes, list):
                continue
            rec = games_by_id.setdefault(str(parent_event), {
                "sport": sport, "eventId": str(parent_event),
                "away": None, "home": None,
                "moneyline": {}, "spread": {}, "total": {},
                "source": "DraftKings Sportsbook"
            })
            ml = re.search(r"money\s*line|moneyline", market_name, re.I)
            sp = re.search(r"spread|run\s*line|handicap", market_name, re.I)
            tot = re.search(r"total|over.?under", market_name, re.I)
            for o in outcomes:
                if not isinstance(o, dict): continue
                label = dk_clean_team(dk_first(o, ["label","name","participant","displayName"]) or "")
                odds = dk_clean_odds(dk_first(o, ["oddsAmerican","americanOdds","odds","price"]))
                line = dk_clean_odds(dk_first(o, ["line","points","handicap","value"]))
                if ml and label and odds:
                    rec["moneyline"][label] = odds
                elif sp and label:
                    rec["spread"][label] = {"line": line, "odds": odds}
                elif tot:
                    low = label.lower()
                    if "over" in low:
                        rec["total"]["line"] = line or re.sub(r"[^0-9.]+","",label)
                        rec["total"]["overOdds"] = odds
                    elif "under" in low:
                        rec["total"].setdefault("line", line or re.sub(r"[^0-9.]+","",label))
                        rec["total"]["underOdds"] = odds

    return [
        g for g in games_by_id.values()
        if g.get("away") and g.get("home") and (g["moneyline"] or g["spread"] or g["total"])
    ]

def dk_parse_sportsbook_visible_text(raw, sport):
    """
    Fallback for server-rendered Sportsbook pages when event lines are visible as text.
    """
    text = dk_plain_text(raw)
    lines = text.splitlines()
    games = []
    # Search windows around matchup-looking lines.
    for i, line in enumerate(lines):
        m = re.match(r"^(.{2,60}?)\s+@\s+(.{2,60}?)$", line)
        if not m:
            continue
        away, home = map(dk_clean_team, m.groups())
        window = "\n".join(lines[i:i+60])
        moneyline, spread, total = {}, {}, {}

        # Accept either table-like "Team -1.5 -110" or separated labels.
        for team in (away, home):
            last = re.escape(team.split()[-1])
            mm = re.search(rf"(?:{re.escape(team)}|{last}).{{0,50}}?([+-]\d{3,4})", window, re.I|re.S)
            if mm: moneyline[team] = dk_clean_odds(mm.group(1))
            sm = re.search(rf"(?:{re.escape(team)}|{last}).{{0,30}}?([+-]\d+(?:\.\d+)?)\s+([+-]\d{3,4})", window, re.I|re.S)
            if sm: spread[team] = {"line":dk_clean_odds(sm.group(1)), "odds":dk_clean_odds(sm.group(2))}
        tm = re.search(r"\bO(?:ver)?\s*(\d+(?:\.\d+)?)\s*([+-]\d{3,4}).*?\bU(?:nder)?\s*\1\s*([+-]\d{3,4})", window, re.I|re.S)
        if tm:
            total = {"line":tm.group(1),"overOdds":dk_clean_odds(tm.group(2)),"underOdds":dk_clean_odds(tm.group(3))}
        if moneyline or spread or total:
            games.append({
                "sport":sport,"away":away,"home":home,
                "moneyline":moneyline,"spread":spread,"total":total,
                "source":"DraftKings Sportsbook"
            })
    return games

def dk_discover_college_volleyball_urls():
    urls = []
    href_re = re.compile(r'href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I|re.S)
    for page in DK_VOLLEYBALL_DISCOVERY:
        try:
            raw = fetch_text(page)
        except Exception:
            continue
        for href, label_html in href_re.findall(raw):
            label = dk_plain_text(label_html).lower()
            href_low = href.lower()
            # Be conservative: NCAA/college + volleyball + women/womens if present.
            if "volleyball" not in href_low and "volleyball" not in label:
                continue
            if any(k in (href_low+" "+label) for k in ["ncaa","college","women","womens"]):
                if href.startswith("/"):
                    href = "https://sportsbook.draftkings.com" + href
                if href.startswith("https://sportsbook.draftkings.com") and href not in urls:
                    urls.append(href)
    return urls

def dk_parse_network_page(raw, sport):
    # Retains the older DK Network text parser only as a fallback.
    text = dk_plain_text(raw)
    game_re = re.compile(
        r"(?m)^(.{2,60}?)\s+@\s+(.{2,60}?)\n(\d{1,2}/\d{1,2},\s*\d{1,2}:\d{2}\s*(?:AM|PM))"
    )
    matches = list(game_re.finditer(text))
    games = []
    for i,m in enumerate(matches):
        away,home = map(dk_clean_team,m.group(1,2))
        body=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        ml,sp,tot={},{},{}
        for team in (away,home):
            cand=re.escape(team.split()[-1])
            mm=re.search(rf"(?:^|\n).*?{cand}\s+([+-]\d+)\b",body,re.I|re.M)
            if mm: ml[team]=dk_clean_odds(mm.group(1))
            sm=re.search(rf"(?:^|\n).*?{cand}\s+([+-]?\d+(?:\.\d+)?)\s+([+-]\d+)\b",body,re.I|re.M)
            if sm: sp[team]={"line":dk_clean_odds(sm.group(1)),"odds":dk_clean_odds(sm.group(2))}
        over=re.search(r"(?:^|\n)Over\s+(\d+(?:\.\d+)?)\s+([+-]\d+)",body,re.I|re.M)
        under=re.search(r"(?:^|\n)Under\s+(\d+(?:\.\d+)?)\s+([+-]\d+)",body,re.I|re.M)
        if over:
            tot={"line":over.group(1),"overOdds":dk_clean_odds(over.group(2))}
        if under:
            tot.setdefault("line",under.group(1));tot["underOdds"]=dk_clean_odds(under.group(2))
        if ml or sp or tot:
            games.append({"sport":sport,"away":away,"home":home,"moneyline":ml,"spread":sp,"total":tot,"source":"DraftKings Network fallback"})
    return games

def refresh_draftkings_odds(data):
    all_games=[]
    seen=set()
    source_pages={}

    # Primary: official DraftKings Sportsbook league pages.
    sources=dict(DK_SPORTSBOOK_SOURCES)
    cvb_urls=dk_discover_college_volleyball_urls()
    if cvb_urls:
        sources["cvb"]=cvb_urls
        source_pages["cvb"]=cvb_urls

    for sport,urls in sources.items():
        source_pages.setdefault(sport,urls)
        for url in urls:
            try:
                raw=fetch_text(url)
                parsed=dk_parse_sportsbook_json(raw,sport)
                if not parsed:
                    parsed=dk_parse_sportsbook_visible_text(raw,sport)
                for g in parsed:
                    key=(sport,dk_clean_team(g.get("away")).lower(),dk_clean_team(g.get("home")).lower())
                    if key in seen: continue
                    seen.add(key);all_games.append(g)
            except Exception as exc:
                print(f"DraftKings Sportsbook source failed ({sport}): {exc}")

    # Fallback only for sports where Sportsbook produced no game lines.
    sports_found={g["sport"] for g in all_games}
    for sport,urls in DK_NETWORK_FALLBACKS.items():
        if sport in sports_found:
            continue
        for url in urls:
            try:
                raw=fetch_text(url)
                for g in dk_parse_network_page(raw,sport):
                    key=(sport,g["away"].lower(),g["home"].lower())
                    if key in seen: continue
                    seen.add(key);all_games.append(g)
            except Exception as exc:
                print(f"DraftKings Network fallback failed ({sport}): {exc}")

    previous=data.get("draftkingsOdds") or {}
    if all_games:
        data["draftkingsOdds"]={
            "updatedAt":datetime.now(timezone.utc).isoformat(),
            "source":"DraftKings",
            "primarySource":"DraftKings Sportsbook",
            "fallbackSource":"DraftKings Network",
            "sourcePages":source_pages,
            "collegeVolleyballDiscovered":bool(cvb_urls),
            "games":all_games,
        }
        print(f"DraftKings Sportsbook odds refreshed: {len(all_games)} games; sports={sorted({g['sport'] for g in all_games})}")
    else:
        print("DraftKings Sportsbook refresh returned no usable game lines; preserving last-good odds.")
        if previous:
            data["draftkingsOdds"]=previous


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

    data["version"] = "v13.9"
    data["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("automation", {})["enabled"] = True
    data["automation"]["lastRun"] = data["lastUpdated"]

    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    JS_PATH.write_text("window.FAVE_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("Dayton Sports data refresh complete.")


if __name__ == "__main__":
    main()
