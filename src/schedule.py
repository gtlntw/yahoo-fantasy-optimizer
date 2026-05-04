"""
MLB Schedule & Starting Pitcher Lookup.

Uses the free MLB Stats API (no key required) to determine:
  - Which MLB teams have a game on a given date
  - Which pitchers are the probable starters

Player dicts from Yahoo are then enriched with:
  - has_game (bool): player's team has a game today
  - is_starting_pitcher (bool): player is the probable SP for their game
  - opponent (str): opponent team name, or "" if no game
"""

import logging
import urllib.request
import urllib.error
import json
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_MLB_SCHEDULE_URL = (
    "https://statsapi.mlb.com/api/v1/schedule"
    "?sportId=1&hydrate=probablePitcher&date={date}"
)


@dataclass
class ScheduleInfo:
    """Aggregate of today's MLB schedule data."""
    # Normalised lowercase team names that have a game (e.g. "new york yankees")
    teams_playing: set[str] = field(default_factory=set)
    # MLB player IDs of probable starting pitchers
    starting_pitcher_ids: set[int] = field(default_factory=set)
    # MLB player full name → opponent team name  (case-insensitive key)
    pitcher_name_to_opponent: dict[str, str] = field(default_factory=dict)
    # Normalised team name → opponent team name
    team_matchups: dict[str, str] = field(default_factory=dict)


def get_schedule(date_str: str) -> ScheduleInfo:
    """
    Fetch the MLB schedule for date_str (YYYY-MM-DD) from the Stats API.

    Returns a ScheduleInfo populated with teams playing, starting pitcher
    IDs (by MLB ID) and names, and team matchup info.

    On any network or parse error the function returns an empty ScheduleInfo
    so downstream code degrades gracefully (defaults: all players have games,
    no pitcher is flagged as starting).
    """
    url = _MLB_SCHEDULE_URL.format(date=date_str)
    logger.info(f"Fetching MLB schedule from: {url}")

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.warning(f"Could not fetch MLB schedule: {exc}. Defaulting to no schedule data.")
        return ScheduleInfo()

    info = ScheduleInfo()

    dates = raw.get("dates", [])
    if not dates:
        logger.info("No games found for date: %s", date_str)
        return info

    for game in dates[0].get("games", []):
        teams = game.get("teams", {})
        away = teams.get("away", {})
        home = teams.get("home", {})

        away_name = away.get("team", {}).get("name", "")
        home_name = home.get("team", {}).get("name", "")

        if away_name:
            info.teams_playing.add(away_name.lower())
            info.team_matchups[away_name.lower()] = home_name
        if home_name:
            info.teams_playing.add(home_name.lower())
            info.team_matchups[home_name.lower()] = away_name

        # Probable pitchers
        for side, opponent_name in [(away, home_name), (home, away_name)]:
            pp = side.get("probablePitcher")
            if pp:
                pid = pp.get("id")
                pname = pp.get("fullName", "")
                if pid:
                    info.starting_pitcher_ids.add(int(pid))
                if pname:
                    info.pitcher_name_to_opponent[pname.lower()] = opponent_name

    logger.info(
        f"Schedule loaded: {len(info.teams_playing)} teams playing, "
        f"{len(info.starting_pitcher_ids)} probable starters identified"
    )
    return info


# ---------------------------------------------------------------------------
# Roster enrichment
# ---------------------------------------------------------------------------

def enrich_roster_with_schedule(
    roster: list[dict],
    schedule: ScheduleInfo,
) -> list[dict]:
    """
    Annotate each player dict with schedule-derived fields:

      has_game (bool)             – player's MLB team has a game today
      is_starting_pitcher (bool)  – player is the probable starter today
      opponent (str)              – opponent team name, "" if no game

    Matching is done by:
      1. MLB player ID stored in `mlb_id` field (most reliable)
      2. Player name string match (fallback for pitchers)
      3. Yahoo `editorial_team_full_name` → MLB team name (for has_game)
    """
    for player in roster:
        team_name = _resolve_team_name(player)
        has_game = team_name in schedule.teams_playing if team_name else False

        # Determine if this SP is in the starting rotation today
        is_starting = False
        if has_game and player.get("position_type") == "P":
            # Try by MLB ID first
            mlb_id = player.get("mlb_id")
            if mlb_id and int(mlb_id) in schedule.starting_pitcher_ids:
                is_starting = True
            else:
                # Fall back to name matching
                full_name = player.get("name", "").lower()
                if full_name in schedule.pitcher_name_to_opponent:
                    is_starting = True

        opponent = ""
        if has_game and team_name:
            opponent = schedule.team_matchups.get(team_name, "")

        player["has_game"] = has_game
        player["is_starting_pitcher"] = is_starting
        player["opponent"] = opponent

    return roster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Map common Yahoo team-name variants → canonical MLB API team name (lowercase)
# Yahoo usually returns the full city+name, but sometimes abbreviated.
_YAHOO_TO_MLB: dict[str, str] = {
    # AL East
    "new york yankees": "new york yankees",
    "boston red sox": "boston red sox",
    "toronto blue jays": "toronto blue jays",
    "tampa bay rays": "tampa bay rays",
    "baltimore orioles": "baltimore orioles",
    # AL Central
    "chicago white sox": "chicago white sox",
    "cleveland guardians": "cleveland guardians",
    "detroit tigers": "detroit tigers",
    "kansas city royals": "kansas city royals",
    "minnesota twins": "minnesota twins",
    # AL West
    "houston astros": "houston astros",
    "los angeles angels": "los angeles angels",
    "oakland athletics": "athletics",
    "sacramento athletics": "athletics",
    "athletics": "athletics",
    "seattle mariners": "seattle mariners",
    "texas rangers": "texas rangers",
    # NL East
    "atlanta braves": "atlanta braves",
    "miami marlins": "miami marlins",
    "new york mets": "new york mets",
    "philadelphia phillies": "philadelphia phillies",
    "washington nationals": "washington nationals",
    # NL Central
    "chicago cubs": "chicago cubs",
    "cincinnati reds": "cincinnati reds",
    "milwaukee brewers": "milwaukee brewers",
    "pittsburgh pirates": "pittsburgh pirates",
    "st. louis cardinals": "st. louis cardinals",
    "st louis cardinals": "st. louis cardinals",
    # NL West
    "arizona diamondbacks": "arizona diamondbacks",
    "colorado rockies": "colorado rockies",
    "los angeles dodgers": "los angeles dodgers",
    "san diego padres": "san diego padres",
    "san francisco giants": "san francisco giants",
}


def _resolve_team_name(player: dict) -> Optional[str]:
    """
    Return the normalised (lowercase) MLB team name for a player, or None.

    Looks at several possible Yahoo field names and normalises them.
    """
    for field in ("editorial_team_full_name", "team_name", "team"):
        raw = player.get(field, "")
        if raw:
            lower = raw.strip().lower()
            # Direct match or map via known aliases
            return _YAHOO_TO_MLB.get(lower, lower)
    return None
