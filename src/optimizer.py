"""
Lineup optimization engine.

Takes AI-ranked players and assigns them to optimal roster positions
respecting position eligibility constraints.
"""

import logging
from copy import deepcopy

logger = logging.getLogger(__name__)

# Define roster slot structure
# Each slot has a name and which positions can fill it
BATTER_SLOTS = [
    {"slot": "C", "eligible": {"C"}},
    {"slot": "1B", "eligible": {"1B"}},
    {"slot": "2B", "eligible": {"2B"}},
    {"slot": "3B", "eligible": {"3B"}},
    {"slot": "SS", "eligible": {"SS"}},
    {"slot": "OF", "eligible": {"OF", "CF", "LF", "RF"}},
    {"slot": "OF", "eligible": {"OF", "CF", "LF", "RF"}},
    {"slot": "OF", "eligible": {"OF", "CF", "LF", "RF"}},
    {"slot": "Util", "eligible": None},  # None = any batter
    {"slot": "Util", "eligible": None},
]

PITCHER_SLOTS = [
    {"slot": "SP", "eligible": {"SP"}},
    {"slot": "SP", "eligible": {"SP"}},
    {"slot": "RP", "eligible": {"RP"}},
    {"slot": "RP", "eligible": {"RP"}},
    {"slot": "P", "eligible": None},  # None = any pitcher
    {"slot": "P", "eligible": None},
    {"slot": "P", "eligible": None},
    {"slot": "P", "eligible": None},
]

# Number of bench, IL, NA slots
BENCH_SLOTS = 5
IL_SLOTS = 3
NA_SLOTS = 1


def optimize_lineup(
    roster: list[dict],
    il_moves_applied: bool = False,
) -> list[dict]:
    """
    Assign players to optimal positions based on AI rankings.
    
    Players should already have 'ai_rank' field from the AI ranker.
    Lower rank = better player = should start.
    
    Args:
        roster: List of player dicts with 'ai_rank' field
        il_moves_applied: Whether IL moves were already made
    
    Returns:
        List of position change dicts:
            {"player_id": id, "player_name": name, "from": old_pos, "to": new_pos, "reason": str}
    """
    # Separate by type
    batters = [p for p in roster if p.get("position_type") == "B"]
    pitchers = [p for p in roster if p.get("position_type") == "P"]
    
    # Sort by AI rank (lower = better)
    batters.sort(key=lambda p: p.get("ai_rank", 999))
    pitchers.sort(key=lambda p: p.get("ai_rank", 999))
    
    # Filter out injured/NA players (they stay in IL/NA slots)
    active_batters = [
        p for p in batters
        if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        and p.get("selected_position") != "NA"
    ]
    active_pitchers = [
        p for p in pitchers
        if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        and p.get("selected_position") != "NA"
    ]
    
    inactive_players = [
        p for p in roster
        if p.get("status", "") in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        or p.get("selected_position") == "NA"
    ]
    
    # Assign batters to batter slots
    batter_assignments = _assign_players_to_slots(active_batters, BATTER_SLOTS)
    
    # Assign pitchers to pitcher slots
    pitcher_assignments = _assign_players_to_slots(active_pitchers, PITCHER_SLOTS)
    
    # Combine assignments
    all_assignments = {**batter_assignments, **pitcher_assignments}
    
    # Determine which players are benched
    assigned_ids = set(all_assignments.keys())
    benched_batters = [p for p in active_batters if p["player_id"] not in assigned_ids]
    benched_pitchers = [p for p in active_pitchers if p["player_id"] not in assigned_ids]
    
    # Build the change list
    changes = []
    
    for player_id, new_pos in all_assignments.items():
        player = _find_player(roster, player_id)
        if player:
            old_pos = player.get("selected_position", "BN")
            if old_pos != new_pos and _is_meaningful_change(old_pos, new_pos):
                changes.append({
                    "player_id": player_id,
                    "player_name": player["name"],
                    "from": old_pos,
                    "to": new_pos,
                    "reason": player.get("ai_reasoning", ""),
                })
    
    # Bench players that should be benched
    for player in benched_batters + benched_pitchers:
        old_pos = player.get("selected_position", "BN")
        if old_pos != "BN" and old_pos not in ("IL", "IL+", "DL", "NA"):
            changes.append({
                "player_id": player["player_id"],
                "player_name": player["name"],
                "from": old_pos,
                "to": "BN",
                "reason": player.get("ai_reasoning", "Lower ranked / no game"),
            })
    
    logger.info(f"Optimizer produced {len(changes)} lineup changes")
    return changes


def _assign_players_to_slots(
    players: list[dict],
    slots: list[dict],
) -> dict[int, str]:
    """
    Assign players to slots using a greedy algorithm with specificity priority.
    
    Strategy:
    1. First, assign players to their most specific eligible position
       (e.g., a C-only player goes to C before a C/1B player)
    2. Then fill remaining slots with the best available players
    
    Args:
        players: Sorted list of players (best first by AI rank)
        slots: List of slot definitions
    
    Returns:
        Dict mapping player_id -> assigned slot name
    """
    assignments = {}  # player_id -> slot
    filled_slots = [False] * len(slots)
    assigned_players = set()
    
    # Phase 1: Assign players with FEW eligible positions first (most constrained)
    # This prevents a versatile player from blocking a position-limited player
    players_by_specificity = sorted(
        players,
        key=lambda p: (
            len(p.get("eligible_positions", [])),  # Less positions = more specific
            p.get("ai_rank", 999),  # Then by AI rank
        )
    )
    
    for player in players_by_specificity:
        if player["player_id"] in assigned_players:
            continue
        
        eligible = set(p for p in player.get("eligible_positions", []))
        
        # Find the best (most specific) slot for this player
        best_slot_idx = None
        best_slot_specificity = float("inf")
        
        for i, slot in enumerate(slots):
            if filled_slots[i]:
                continue
            
            # Check if player can fill this slot
            if slot["eligible"] is None:  # Util or P slot - any player
                # Prefer specific slots first, so give Util/P low priority
                if best_slot_idx is None:
                    best_slot_idx = i
                    best_slot_specificity = 999  # Low priority for flex slots
            elif eligible & slot["eligible"]:  # Player is eligible
                slot_specificity = len(slot["eligible"])
                if slot_specificity < best_slot_specificity:
                    best_slot_idx = i
                    best_slot_specificity = slot_specificity
        
        if best_slot_idx is not None:
            assignments[player["player_id"]] = slots[best_slot_idx]["slot"]
            filled_slots[best_slot_idx] = True
            assigned_players.add(player["player_id"])
    
    # Phase 2: Fill remaining slots with best available (by AI rank)
    remaining_players = [p for p in players if p["player_id"] not in assigned_players]
    remaining_players.sort(key=lambda p: p.get("ai_rank", 999))
    
    for player in remaining_players:
        eligible = set(p for p in player.get("eligible_positions", []))
        
        for i, slot in enumerate(slots):
            if filled_slots[i]:
                continue
            
            if slot["eligible"] is None or eligible & slot["eligible"]:
                assignments[player["player_id"]] = slots[i]["slot"]
                filled_slots[i] = True
                assigned_players.add(player["player_id"])
                break
    
    return assignments



# Pitcher slots that are all "generic active pitcher" — any SP/RP can fill them.
# Moving between these slots has zero real-world impact on scoring.
_PITCHER_FLEX_SLOTS = {"SP", "RP", "P"}
# Batter flex slots (Util can hold any position)
_BATTER_FLEX_SLOTS = {"Util"}


def _is_meaningful_change(old_pos: str, new_pos: str) -> bool:
    """
    Return True only if moving from old_pos to new_pos actually matters.

    Suppresses no-op swaps like:
    - SP ↔ P  (both are active pitcher slots; Yahoo scoring is identical)
    - RP ↔ P
    - SP ↔ RP (these matter for slot eligibility but not for scoring output)

    A change is meaningful when:
    - It involves the bench (BN) or IL — going active ↔ bench always matters.
    - It moves a pitcher OUT of the pitcher-flex group entirely.
    - It moves a batter into/out of a dedicated positional slot (C, 1B, SS, …).
    """
    # BN / IL transitions always matter
    special = {"BN", "IL", "IL10", "IL15", "IL60", "DL", "IL-LT", "NA"}
    if old_pos in special or new_pos in special:
        return True

    # Swapping within the same pitcher flex group is a no-op
    if old_pos in _PITCHER_FLEX_SLOTS and new_pos in _PITCHER_FLEX_SLOTS:
        return False

    # Swapping within batter Util slots is also a no-op
    if old_pos in _BATTER_FLEX_SLOTS and new_pos in _BATTER_FLEX_SLOTS:
        return False

    return True


def _find_player(roster: list[dict], player_id: int) -> dict:
    """Find a player in the roster by ID."""
    for player in roster:
        if player.get("player_id") == player_id:
            return player
    return None


def format_changes(changes: list[dict]) -> str:
    """Format lineup changes for display."""
    if not changes:
        return "✅ No lineup changes needed — current lineup is optimal!"
    
    lines = ["⚾ Lineup Changes:"]
    
    # Separate starters and benched
    starting = [c for c in changes if c["to"] != "BN"]
    benching = [c for c in changes if c["to"] == "BN"]
    
    if starting:
        for change in starting:
            arrow = "⬆️" if change["from"] == "BN" else "🔄"
            reason = f"  [{change['reason']}]" if change.get("reason") else ""
            lines.append(
                f"  {arrow} {change['player_name']:25s} "
                f"{change['from']:4s} → {change['to']:4s}{reason}"
            )
    
    if benching:
        for change in benching:
            reason = f"  [{change['reason']}]" if change.get("reason") else ""
            lines.append(
                f"  ⬇️ {change['player_name']:25s} "
                f"{change['from']:4s} → BN{reason}"
            )
    
    return "\n".join(lines)
