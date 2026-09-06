"""
AI-powered player ranking using Gemini.

Analyzes players based on stats, matchups, and category priorities
to produce an optimized daily ranking.
"""

import json
import logging
import os
from typing import Optional, Union

from google import genai
from google.genai import types
from pydantic import BaseModel

from .standings import CategoryGap, CategoryPriority, build_priority_context

logger = logging.getLogger(__name__)

class PlayerRanking(BaseModel):
    player_id: Union[int, str]
    rank: int
    reasoning: str

class AddDropSuggestion(BaseModel):
    drop_player_id: int
    add_player_id: int
    drop_player_name: str
    add_player_name: str
    rationale: str
    expected_category_impact: str

# Module-level client, initialized by configure_gemini()
_client: genai.Client = None


def configure_gemini(api_key: str = None):
    """Configure the Gemini API client."""
    global _client
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError(
            "Gemini API key not set. Either pass api_key or set "
            "GEMINI_API_KEY environment variable."
        )
    _client = genai.Client(api_key=key)


def rank_players(
    roster: list[dict],
    category_gaps: list[CategoryGap],
    date_str: str,
    model_name: str = "gemini-3.8-flash",
    recent_stats: dict = None,
) -> list[dict]:
    """
    Use Gemini to rank players by expected daily fantasy value.
    
    Args:
        roster: List of player dicts from the Yahoo API
        category_gaps: Category gap analysis from standings module
        date_str: The date being optimized (e.g., "2026-04-01")
        model_name: Gemini model to use
    
    Returns:
        List of player dicts sorted by AI ranking, with added 'ai_rank'
        and 'ai_reasoning' fields
    """
    if recent_stats is None:
        recent_stats = {}
        
    # Separate batters and pitchers
    batters = [p for p in roster if p.get("position_type") == "B"]
    pitchers = [p for p in roster if p.get("position_type") == "P"]
    
    ranked = []
    
    if batters:
        ranked_batters = _rank_group(batters, category_gaps, date_str, "batter", model_name, recent_stats)
        ranked.extend(ranked_batters)
    
    if pitchers:
        ranked_pitchers = _rank_group(pitchers, category_gaps, date_str, "pitcher", model_name, recent_stats)
        ranked.extend(ranked_pitchers)
    
    return ranked


def _rank_group(
    players: list[dict],
    category_gaps: list[CategoryGap],
    date_str: str,
    player_type: str,
    model_name: str,
    recent_stats: dict,
) -> list[dict]:
    """Rank a group of players (batters or pitchers) using Gemini."""
    
    priority_context = build_priority_context(category_gaps)
    
    # Build player info for the prompt
    player_info = []
    for p in players:
        info = {
            "player_id": p.get("player_id"),
            "name": p.get("name"),
            "eligible_positions": p.get("eligible_positions", []),
            "selected_position": p.get("selected_position"),
            "status": p.get("status", "healthy"),
            "has_game": p.get("has_game", True),
            "is_starting_pitcher": p.get("is_starting_pitcher", False),
            "opponent": p.get("opponent", ""),
            "recent_stats": recent_stats.get(p.get("player_id"), {}),
        }
        player_info.append(info)
    
    if player_type == "batter":
        categories = "R, HR, RBI, SB, BB, TB, AVG"
    else:
        categories = "W, SV, K, ERA, WHIP, QS"
    
    prompt = f"""You are an expert fantasy baseball analyst optimizing a Rotisserie league lineup.

DATE: {date_str}

SCORING CATEGORIES ({player_type}s): {categories}

{priority_context}

PLAYERS TO RANK:
{json.dumps(player_info, indent=2, ensure_ascii=False)}

TASK: Rank these {player_type}s from BEST to WORST for today's lineup.
Your ranking determines who STARTS (plays today) vs who sits on the BENCH.
The slot assignment (SP/RP/P or Util) is handled automatically — focus ONLY on which players produce the most value today.

Rank based on:
1. `has_game` field: if False, rank LAST — player's team has NO GAME TODAY (reason: "No game today")
2. For pitchers: `is_starting_pitcher` field: if True, player IS the probable SP today and ranks far higher than SPs not starting. If False and the player is an SP, rank them BELOW all RPs who have games (reason: "Not in starting rotation today")
3. Player quality and expected production for today's game vs the named `opponent`
4. Category priority weights (prioritize HIGH categories)
5. Performance trends based on the `recent_stats` field (which contains `season`, `lastweek` [7-day], `last14` [14-day], and `lastmonth` [30-day] stats). 
   - For Batters: evaluate short-term form and momentum using last 7-day (`lastweek`) and 14-day (`last14`) stats alongside season baseline (`season`).
   - For Pitchers: evaluate recent form using 14-day (`last14`) and 30-day (`lastmonth`) stats alongside season baseline (`season`). Favor pitchers on hot streaks and penalize those in deep slumps.
6. Injury status (injured/IL players ranked last)
7. For relievers: whether they are in a high-leverage/save opportunity role

IMPORTANT RULES:
- `has_game == false` → rank LAST, reasoning must say "No game today"
- `is_starting_pitcher == false` AND player is SP-eligible → rank below ALL RPs with games; reasoning should say "Not in starting rotation today"
- Players with status "IL", "IL10", "IL15", "IL60", "DL" should be ranked LAST (they cannot play)
- Players with status "DTD" should be ranked lower but not excluded
- Prioritize players who contribute to 🔴 HIGH priority categories
- For ⚠️ PROTECT categories (rate stats like ERA/WHIP/AVG), be cautious about starting players who might hurt the stat
- Do NOT suggest slot changes (SP→P etc.) — just rank who should play

Rank ALL players, from 1 (best/start) to {len(players)} (worst/bench).
"""
    
    try:
        response = _client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=list[PlayerRanking],
            ),
        )
        
        # Parse the JSON response
        response_text = response.text.strip()
        rankings = json.loads(response_text)
        
        # Merge rankings back into player dicts
        rank_map = {str(r["player_id"]): r for r in rankings}
        for player in players:
            pid_str = str(player.get("player_id", ""))
            if pid_str in rank_map:
                player["ai_rank"] = rank_map[pid_str]["rank"]
                player["ai_reasoning"] = rank_map[pid_str].get("reasoning", "")
            else:
                player["ai_rank"] = len(players)  # Unranked goes last
                player["ai_reasoning"] = "Not ranked by AI"
        
        # Sort by AI rank
        players.sort(key=lambda p: p.get("ai_rank", 999))
        logger.info(f"AI ranked {len(players)} {player_type}s successfully")
        
        return players
        
    except Exception as e:
        logger.warning(f"Gemini ranking failed: {e}. Falling back to stat-based ranking.")
        return fallback_ranking(players)


def fallback_ranking(players: list[dict], category_gaps: list = None) -> list[dict]:
    """
    Daily rotation- and schedule-aware ranking without relying on static season ranks.
    
    Prioritizes:
    1. Having a game today (off-day players are benched)
    2. Injury status (healthy > DTD > IL)
    3. Rotation context for pitchers:
       - Confirmed starting pitchers on the mound today (is_starting_pitcher=True)
       - Active relievers (RP) with games today (Saves, Ks, ERA/WHIP opportunities)
       - Non-starting SPs (produce 0 stats today)
    4. Starter stability:
       - Preserves active starting slots unless an off-day, injury, or confirmed
         starting pitcher on the mound warrants a lineup change.
    """
    def sort_key(player):
        # 1. Having a game today (0 = has game, 1000 = off-day)
        has_game_score = 0 if player.get("has_game", True) else 1000

        # 2. Injury status
        status = player.get("status", "")
        if status in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT"):
            injury_score = 300
        elif status == "DTD":
            injury_score = 60
        else:
            injury_score = 0

        # 3. Rotation context for Pitchers:
        # Confirmed starting pitcher on mound today gets top priority (-100)
        # Active relief pitcher gets high priority (-40)
        # Non-starting SP gets penalty (+100) because they produce 0 stats today
        rotation_score = 0
        if player.get("position_type") == "P":
            is_sp = "SP" in player.get("eligible_positions", [])
            is_rp = "RP" in player.get("eligible_positions", [])
            if player.get("is_starting_pitcher", False):
                rotation_score = -100  # Confirmed starter on the mound!
            elif is_rp:
                rotation_score = -40   # Active reliever can earn SV/K/ERA/WHIP
            elif is_sp:
                rotation_score = 100   # Off-day SP: produces 0 stats today

        # 4. Performance & manager consensus tiebreaker (percent_started from Yahoo)
        # Higher percent_started gives a more negative score (higher priority)
        # E.g. 85% started -> -85 score; 10% started -> -10 score
        pct_started = player.get("percent_started", 0.0) or 0.0
        pct_score = -float(pct_started)

        # 5. Deterministic tiebreaker by name
        name_tiebreaker = player.get("name", "")

        return (has_game_score, injury_score, rotation_score, pct_score, name_tiebreaker)

    players.sort(key=sort_key)
    
    for i, player in enumerate(players):
        player["ai_rank"] = i + 1
        pos_type = player.get("position_type")
        if pos_type == "P":
            if player.get("is_starting_pitcher"):
                player["ai_reasoning"] = "Confirmed starting pitcher on mound today"
            elif "RP" in player.get("eligible_positions", []):
                player["ai_reasoning"] = "Active reliever (SV/K/ERA opportunity)"
            else:
                player["ai_reasoning"] = "Non-starting SP today"
        else:
            if not player.get("has_game", True):
                player["ai_reasoning"] = "No game today"
            elif player.get("status") in ("IL", "IL10", "IL15", "IL60", "DL"):
                player["ai_reasoning"] = f"Injured ({player.get('status')})"
            else:
                player["ai_reasoning"] = "Active starter with game today"
    
    return players


def suggest_add_drops(
    drop_candidates: list[dict],
    free_agents: list[dict],
    category_gaps: list[CategoryGap],
    recent_stats: dict,
    model_name: str = "gemini-3.8-flash",
) -> list[dict]:
    """
    Use Gemini to suggest add/drop transactions.
    
    Args:
        drop_candidates: List of lowest ranked players on the roster
        free_agents: List of top available free agents
        category_gaps: Category analysis showing team weaknesses
        recent_stats: Dict of recent player stats
        model_name: Gemini model to use
        
    Returns:
        List of suggested transaction dicts
    """
    if not _client:
        logger.warning("Gemini client not configured. Skipping add/drop suggestions.")
        return []
        
    if not drop_candidates or not free_agents:
        return []

    priority_context = build_priority_context(category_gaps)
    
    # Build info dicts for the prompt
    def _build_info(p):
        pid = p.get("player_id")
        p_stats = recent_stats.get(pid, {}) or recent_stats.get(str(pid), {})
        return {
            "player_id": pid,
            "name": p.get("name"),
            "positions": p.get("eligible_positions", []),
            "position_type": p.get("position_type"),
            "status": p.get("status", "healthy"),
            "percent_owned": p.get("percent_owned", 0), # if available
            "recent_stats": p_stats,
        }
        
    drops_info = [_build_info(p) for p in drop_candidates]
    adds_info = [_build_info(p) for p in free_agents]
    
    prompt = f"""You are an expert fantasy baseball GM optimizing a Rotisserie league roster.

{priority_context}

YOUR EXPENDABLE PLAYERS (DROP CANDIDATES):
{json.dumps(drops_info, indent=2, ensure_ascii=False)}

TOP AVAILABLE FREE AGENTS:
{json.dumps(adds_info, indent=2, ensure_ascii=False)}

TASK: Analyze the free agents and compare them to the drop candidates. 
Identify up to 3 highly recommended ADD/DROP transactions that would significantly improve the team in its WEAKEST categories.
Only suggest a transaction if the free agent is a CLEAR UPGRADE over the drop candidate based on their long-term value (season stats) and recent momentum (last 7 days and last 30 days) combined with category needs.
Do NOT suggest dropping an injured player (IL) unless they are out for the season, because they can be stashed on the IL instead. Focus on dropping healthy but underperforming bench players.

Return your suggestions as a JSON array matching this schema:
[
  {{
    "drop_player_id": 123,
    "add_player_id": 456,
    "drop_player_name": "Player A",
    "add_player_name": "Player B",
    "rationale": "Clear explanation of why this upgrade helps the team's weak categories.",
    "expected_category_impact": "e.g., +SB, +AVG"
  }}
]
If no clear upgrades are found, return an empty array [].
"""

    try:
        response = _client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=list[AddDropSuggestion],
            ),
        )
        
        response_text = response.text.strip()
        suggestions = json.loads(response_text)
        logger.info(f"AI suggested {len(suggestions)} add/drop transactions")
        return suggestions
        
    except Exception as e:
        logger.warning(f"Gemini add/drop suggestion failed: {e}")
        return []

