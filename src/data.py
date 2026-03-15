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


def get_roster(team: yfa.Team, date: Optional[datetime.date] = None) -> list[dict]:
    """
    Fetch the team roster for a given date.
    
    Args:
        team: Yahoo Fantasy Team object
        date: Date to get roster for. Defaults to today.
    
    Returns:
        List of player dicts with keys:
            player_id, name, position_type, eligible_positions,
            selected_position, status
    """
    if date is None:
        date = datetime.date.today()
    
    logger.info(f"Fetching roster for {date}...")
    roster = team.roster(day=date)
    
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
