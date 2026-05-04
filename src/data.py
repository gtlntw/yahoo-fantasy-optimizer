"""
Data fetching module.

Retrieves roster, player stats, and matchup data from
Yahoo Fantasy API and pybaseball.
"""

import datetime
import logging
from typing import Optional

import yahoo_fantasy_api as yfa

logger = logging.getLogger(__name__)


# Roster position categories
BATTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF", "Util"}
PITCHER_POSITIONS = {"SP", "RP", "P"}
INACTIVE_POSITIONS = {"BN", "IL", "IL+", "NA", "DL"}


def get_roster(team: yfa.Team, date: Optional[datetime.date] = None, league: Optional[yfa.League] = None) -> list[dict]:
    """
    Fetch the team roster for a given date.
    
    Args:
        team: Yahoo Fantasy Team object
        date: Date to get roster for. Defaults to today.
        league: Optional Yahoo Fantasy League object. If provided, used to fetch
                MLB team names (editorial_team_full_name) which are missing from the raw roster.
    
    Returns:
        List of player dicts with keys:
            player_id, name, position_type, eligible_positions,
            selected_position, status, editorial_team_full_name (if league provided)
    """
    if date is None:
        date = datetime.date.today()
    
    logger.info(f"Fetching roster for {date}...")
    roster = team.roster(day=date)
    
    # If league is provided, fetch detailed player info to get their real-life MLB team
    if league and roster:
        try:
            logger.info("  Enriching roster with MLB team names from player details...")
            pids = [p["player_id"] for p in roster]
            details = league.player_details(pids)
            
            # Create a lookup dict for fast merging
            team_lookup = {}
            for d in details:
                if "player_id" in d and "editorial_team_full_name" in d:
                    team_lookup[str(d["player_id"])] = d["editorial_team_full_name"]
            
            # Attach to roster
            for player in roster:
                pid = str(player.get("player_id", ""))
                if pid in team_lookup:
                    player["editorial_team_full_name"] = team_lookup[pid]
        except Exception as e:
            logger.warning(f"  Failed to fetch player details for team names: {e}")
    
    logger.info(f"  Found {len(roster)} players on roster")
    for player in roster:
        pos = player.get("selected_position", "?")
        status = player.get("status", "")
        status_str = f" [{status}]" if status else ""
        logger.debug(f"  {player['name']:25s} | {pos:4s}{status_str}")
    
    return roster


def get_league_settings(league: yfa.League) -> dict:
    """
    Fetch league settings including stat categories and roster positions.
    
    Returns:
        Dict with league configuration
    """
    settings = league.settings()
    logger.info(f"League settings loaded: {settings.get('name', 'Unknown League')}")
    return settings


def get_standings(league: yfa.League) -> list[dict]:
    """
    Fetch current league standings.
    
    Returns:
        List of team standings with stats per category
    """
    # The default league.standings() strips out stats, so we fetch raw:
    try:
        raw = league.yhandler.get(f"league/{league.league_id}/standings")
        teams_dict = raw["fantasy_content"]["league"][1]["standings"][0]["teams"]
        
        # Ensure stats_id_map is loaded
        if not hasattr(league, 'stats_id_map') or not league.stats_id_map:
            league._cache_stats_id_map(league.settings()['game_code'])
            
        stats_map = league.stats_id_map
        
        standings = []
        for key, team_wrapper in teams_dict.items():
            if key == "count":
                continue
                
            team_data = team_wrapper["team"]
            team_info = {}
            
            # Extract basic info
            if isinstance(team_data[0], list):
                for item in team_data[0]:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            team_info[k] = v
            
            # Extract standings and stats
            extracted_stats = {}
            for item in team_data:
                if isinstance(item, dict):
                    if "team_standings" in item:
                        team_info["rank"] = item["team_standings"].get("rank")
                    elif "team_stats" in item:
                        raw_stats = item["team_stats"].get("stats", [])
                        for s in raw_stats:
                            stat_obj = s.get("stat", {})
                            stat_id = stat_obj.get("stat_id")
                            val = stat_obj.get("value")
                            
                            # Map stat_id to category name using league map
                            try:
                                stat_id_int = int(stat_id)
                                if stat_id_int in stats_map:
                                    cat_name = stats_map[stat_id_int]
                                    extracted_stats[cat_name] = val
                            except (ValueError, TypeError):
                                pass
            
            # Put stats directly in the team_info dict for _extract_stat to find
            team_info["stats"] = extracted_stats
            standings.append(team_info)
            
        logger.info(f"Fetched standings for {len(standings)} teams")
        return standings
        
    except Exception as e:
        logger.warning(f"Failed to fetch raw standings: {e}. Falling back to default.")
        standings = league.standings()
        logger.info(f"Fetched standings for {len(standings)} teams")
        return standings


def get_free_agents(league: yfa.League, position: str = "B") -> list[dict]:
    """
    Fetch free agents for a given position.
    
    Args:
        position: Position code (e.g., 'B' for all batters, 'P' for pitchers,
                  or specific like 'C', 'SP', etc.)
    
    Returns:
        List of free agent player dicts
    """
    logger.info(f"Fetching free agents for position: {position}...")
    free_agents = league.free_agents(position)
    logger.info(f"  Found {len(free_agents)} free agents")
    return free_agents


def categorize_roster(roster: list[dict]) -> dict:
    """
    Categorize roster players into groups for optimization.
    
    Args:
        roster: Full roster from get_roster()
    
    Returns:
        Dict with keys:
            - active_batters: batters in starting positions
            - active_pitchers: pitchers in starting positions
            - bench: players on bench
            - injured: players on IL/DL
            - na: players on NA list
            - all_batters: all batters regardless of position
            - all_pitchers: all pitchers regardless of position
    """
    result = {
        "active_batters": [],
        "active_pitchers": [],
        "bench": [],
        "injured": [],
        "na": [],
        "all_batters": [],
        "all_pitchers": [],
    }
    
    for player in roster:
        pos = player.get("selected_position", "BN")
        pos_type = player.get("position_type", "")
        
        # Categorize by selected position
        if pos == "BN":
            result["bench"].append(player)
        elif pos in ("IL", "IL+", "DL"):
            result["injured"].append(player)
        elif pos == "NA":
            result["na"].append(player)
        elif pos in BATTER_POSITIONS:
            result["active_batters"].append(player)
        elif pos in PITCHER_POSITIONS:
            result["active_pitchers"].append(player)
        
        # Also categorize by player type
        if pos_type == "B":
            result["all_batters"].append(player)
        elif pos_type == "P":
            result["all_pitchers"].append(player)
    
    logger.info(
        f"Roster breakdown: {len(result['active_batters'])} starting batters, "
        f"{len(result['active_pitchers'])} starting pitchers, "
        f"{len(result['bench'])} bench, {len(result['injured'])} IL"
    )
    
    return result


def is_player_injured(player: dict) -> bool:
    """Check if a player has an injury status that makes them IL-eligible."""
    status = player.get("status", "")
    return status in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")


def is_player_day_to_day(player: dict) -> bool:
    """Check if a player is day-to-day."""
    status = player.get("status", "")
    return status in ("DTD",)


def has_game_today(player: dict) -> bool:
    """
    Check if a player has a game today.
    
    The Yahoo API includes game info in the roster data. Players
    without a game will typically not have game-related fields or
    will show as not playing.
    
    Note: The yahoo_fantasy_api roster() data may include a
    'has_game' or similar field. We also infer from status.
    """
    # Players on IL/NA never "have a game" for lineup purposes
    if is_player_injured(player):
        return False
    
    # Check for explicit game status if available in the data
    # The Yahoo API doesn't always include this directly,
    # so we default to True for healthy players and let the
    # AI ranker handle the rest based on schedule data
    return True


def get_player_stats(league: yfa.League, player_ids: list[int]) -> dict:
    """
    Get stats for a list of players.
    
    Args:
        league: Yahoo Fantasy League object
        player_ids: List of Yahoo player IDs
    
    Returns:
        Dict mapping player_id -> stats dict
    """
    # Yahoo API provides player stats through the league
    # We can use percent_owned and player_details for additional info
    stats = {}
    try:
        ownership = league.ownership(player_ids)
        for pid, info in ownership.items():
            stats[int(pid)] = info
    except Exception as e:
        logger.warning(f"Could not fetch player stats: {e}")
    
    return stats


def get_recent_stats(league: yfa.League, roster: list[dict]) -> dict:
    """
    Fetch recent stats for players to determine their recent form.
    Batters: lastweek, lastmonth
    Pitchers: lastmonth
    
    Note: yahoo_fantasy_api only supports 'lastweek' (7 days) and 'lastmonth' (30 days).
    """
    # Separate player IDs by type
    batter_ids = []
    pitcher_ids = []
    
    for p in roster:
        pid = p.get("player_id")
        if not pid:
            continue
        # In yfa, 'B' means batter, 'P' means pitcher
        if p.get("position_type") == "B":
            batter_ids.append(pid)
        elif p.get("position_type") == "P":
            pitcher_ids.append(pid)
            
    stats_dict = {p.get("player_id"): {} for p in roster if p.get("player_id")}
    
    # Helper to merge stats into the main dict
    def merge_stats(player_ids, req_type):
        if not player_ids:
            return
        logger.info(f"  Fetching {req_type} stats for {len(player_ids)} players...")
        try:
            # player_stats handles chunking automatically under the hood
            res = league.player_stats(player_ids, req_type)
            for row in res:
                pid = row.get("player_id")
                if pid and pid in stats_dict:
                    # Filter out unnecessary info, just keep the actual stats
                    clean_row = {k: v for k, v in row.items() if k not in ("player_id", "name", "position_type")}
                    stats_dict[pid][req_type] = clean_row
        except Exception as e:
            logger.warning(f"Failed to fetch {req_type} stats: {e}")

    logger.info("Fetching recent player stats...")
    if batter_ids:
        merge_stats(batter_ids, "lastweek")
        merge_stats(batter_ids, "lastmonth")
        
    if pitcher_ids:
        merge_stats(pitcher_ids, "lastweek")
        merge_stats(pitcher_ids, "lastmonth")
        
    return stats_dict
