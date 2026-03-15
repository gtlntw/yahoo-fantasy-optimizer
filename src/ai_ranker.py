"""
AI-powered player ranking using Gemini.

Analyzes players based on stats, matchups, and category priorities
to produce an optimized daily ranking.
"""

import json
import logging
import os
from typing import Optional

from google import genai

from .standings import CategoryGap, CategoryPriority, build_priority_context

logger = logging.getLogger(__name__)

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
    model_name: str = "gemini-3.1-pro-preview",
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
    # Separate batters and pitchers
    batters = [p for p in roster if p.get("position_type") == "B"]
    pitchers = [p for p in roster if p.get("position_type") == "P"]
    
    ranked = []
    
    if batters:
        ranked_batters = _rank_group(batters, category_gaps, date_str, "batter", model_name)
        ranked.extend(ranked_batters)
    
    if pitchers:
        ranked_pitchers = _rank_group(pitchers, category_gaps, date_str, "pitcher", model_name)
        ranked.extend(ranked_pitchers)
    
    return ranked


def _rank_group(
    players: list[dict],
    category_gaps: list[CategoryGap],
    date_str: str,
    player_type: str,
    model_name: str,
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
{json.dumps(player_info, indent=2)}

TASK: Rank these {player_type}s from best to worst for today's lineup based on:
1. Whether the player likely has a game today
2. Player quality and expected production
3. Category priority weights (prioritize HIGH categories)
4. Injury status (injured players ranked last)
5. For pitchers: whether they are likely starting today (SP) or in a high-leverage role (RP/closer)

IMPORTANT RULES:
- Players with status "IL", "IL10", "IL15", "IL60", "DL" should be ranked LAST (they cannot play)
- Players with status "DTD" should be ranked lower but not excluded
- Prioritize players who contribute to 🔴 HIGH priority categories
- For ⚠️ PROTECT categories (rate stats), be cautious about starting players who might hurt the stat

Return ONLY a JSON array with this format, no other text:
[
  {{"player_id": <id>, "rank": 1, "reasoning": "<brief reason>"}},
  ...
]

Rank ALL players, from 1 (best/start) to {len(players)} (worst/bench).
"""
    
    try:
        response = _client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        
        # Parse the JSON response
        response_text = response.text.strip()
        # Remove markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])
        
        rankings = json.loads(response_text)
        
        # Merge rankings back into player dicts
        rank_map = {r["player_id"]: r for r in rankings}
        for player in players:
            pid = player.get("player_id")
            if pid in rank_map:
                player["ai_rank"] = rank_map[pid]["rank"]
                player["ai_reasoning"] = rank_map[pid].get("reasoning", "")
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


def fallback_ranking(players: list[dict]) -> list[dict]:
    """
    Simple stat-based ranking when AI is unavailable.
    
    Prioritizes:
    1. Healthy players over injured
    2. Players who are not on bench/IL
    3. Alphabetical as tiebreaker
    """
    def sort_key(player):
        status = player.get("status", "")
        # Injured players go last
        if status in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT"):
            injury_score = 100
        elif status == "DTD":
            injury_score = 50
        else:
            injury_score = 0
        
        return (injury_score, player.get("name", ""))
    
    players.sort(key=sort_key)
    
    for i, player in enumerate(players):
        player["ai_rank"] = i + 1
        player["ai_reasoning"] = "Stat-based fallback ranking"
    
    return players
