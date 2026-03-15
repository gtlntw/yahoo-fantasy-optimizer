"""
IL (Injured List) Auto-Management.

Automatically moves injured players to IL slots and activates
healthy players from IL, freeing roster spots for the optimizer.
"""

import datetime
import logging
from typing import Optional

import yahoo_fantasy_api as yfa

logger = logging.getLogger(__name__)

# Statuses that make a player IL-eligible
IL_ELIGIBLE_STATUSES = {"IL", "IL10", "IL15", "IL60", "DL", "IL-LT"}

# IL slot names in Yahoo
IL_SLOT_NAMES = {"IL", "IL+", "DL"}


def manage_il(
    team: yfa.Team,
    roster: list[dict],
    date: Optional[datetime.date] = None,
    dry_run: bool = True,
) -> list[dict]:
    """
    Auto-manage IL slots: move injured players to IL, activate healthy ones.
    
    Args:
        team: Yahoo Fantasy Team object
        roster: Current roster from data.get_roster()
        date: Date for the roster changes. Defaults to today.
        dry_run: If True, only report changes without applying them.
    
    Returns:
        List of IL move dicts:
            {"player": name, "action": "to_il"|"activate", "from": pos, "to": pos}
    """
    if date is None:
        date = datetime.date.today()
    
    moves = []
    
    # Step 1: Find IL-eligible injured players NOT already on IL
    players_needing_il = []
    players_on_il = []
    il_slots_used = 0
    il_slots_total = 3  # Default, could be read from league settings
    
    for player in roster:
        selected_pos = player.get("selected_position", "")
        status = player.get("status", "")
        
        if selected_pos in IL_SLOT_NAMES:
            il_slots_used += 1
            # Check if this player is healthy now (activated from IL)
            if status not in IL_ELIGIBLE_STATUSES and status != "DTD":
                players_on_il.append(player)  # Healthy, should activate
            else:
                players_on_il.append(player)  # Still injured, keep on IL
        elif status in IL_ELIGIBLE_STATUSES:
            players_needing_il.append(player)
    
    il_slots_available = il_slots_total - il_slots_used
    
    # Step 2: Activate healthy players from IL
    for player in players_on_il:
        status = player.get("status", "")
        if status not in IL_ELIGIBLE_STATUSES and status != "DTD":
            move = {
                "player_id": player["player_id"],
                "player": player["name"],
                "action": "activate",
                "from": player.get("selected_position", "IL"),
                "to": "BN",  # Move to bench, optimizer will place them
                "reason": f"No longer injured (status: {status or 'healthy'})",
            }
            moves.append(move)
            il_slots_available += 1
            logger.info(f"🏥 ACTIVATE: {player['name']} → BN (healthy)")
    
    # Step 3: Move injured players to IL slots
    for player in players_needing_il:
        if il_slots_available > 0:
            move = {
                "player_id": player["player_id"],
                "player": player["name"],
                "action": "to_il",
                "from": player.get("selected_position", "BN"),
                "to": "IL",
                "reason": f"Injured ({player.get('status', 'unknown')})",
            }
            moves.append(move)
            il_slots_available -= 1
            logger.info(
                f"🏥 TO IL: {player['name']} ({player.get('status')}) "
                f"→ IL slot"
            )
        else:
            logger.warning(
                f"⚠️  {player['name']} is injured ({player.get('status')}) "
                f"but no IL slots available! Manual action needed."
            )
    
    # Step 4: Apply moves if not dry run
    if moves and not dry_run:
        _apply_il_moves(team, moves, date)
    
    if not moves:
        logger.info("🏥 No IL moves needed.")
    
    return moves


def _apply_il_moves(
    team: yfa.Team,
    moves: list[dict],
    date: datetime.date,
):
    """Apply IL moves via the Yahoo API."""
    modified_lineup = []
    
    for move in moves:
        modified_lineup.append({
            "player_id": move["player_id"],
            "selected_position": move["to"],
        })
    
    if modified_lineup:
        try:
            team.change_positions(date, modified_lineup)
            logger.info(f"✅ Applied {len(modified_lineup)} IL moves")
        except Exception as e:
            logger.error(f"❌ Failed to apply IL moves: {e}")
            raise


def format_il_moves(moves: list[dict]) -> str:
    """Format IL moves for display."""
    if not moves:
        return "🏥 No IL moves needed."
    
    lines = ["🏥 IL Moves:"]
    for move in moves:
        if move["action"] == "to_il":
            lines.append(
                f"  {move['player']:25s} → IL  "
                f"(was {move['from']}, {move['reason']})"
            )
        elif move["action"] == "activate":
            lines.append(
                f"  {move['player']:25s} → BN  "
                f"(was IL, {move['reason']})"
            )
    
    return "\n".join(lines)
