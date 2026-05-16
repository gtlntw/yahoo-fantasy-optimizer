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
        and p.get("has_game", True)  # bench batters with no game today
    ]
    # Batters whose team has no game today — force to bench
    no_game_batters = [
        p for p in batters
        if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        and p.get("selected_position") != "NA"
        and not p.get("has_game", True)
    ]
    # Healthy pitchers are split into three tiers:
    #  1. SPs who are starting today + all RPs (fill active slots first)
    #  2. SPs NOT in the starting rotation today (fill P flex only / bench)
    # All injured pitchers go to inactive_players as before.
    # Healthy pitchers: have a game today
    healthy_pitchers = [
        p for p in pitchers
        if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        and p.get("selected_position") != "NA"
        and p.get("has_game", True)
    ]
    # No game pitchers: no game today
    no_game_pitchers = [
        p for p in pitchers
        if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        and p.get("selected_position") != "NA"
        and not p.get("has_game", True)
    ]

    # Build priority-ordered pitcher list:
    # Starting SPs and all RPs first, non-starting SPs last
    def _is_sp(p):
        positions = set(p.get("eligible_positions", []))
        return bool(positions & {"SP"})

    active_pitchers_primary = [
        p for p in healthy_pitchers
        if not _is_sp(p) or p.get("is_starting_pitcher", False)
    ]
    for p in active_pitchers_primary: p["_sort_priority"] = 0
    
    # Secondary pitchers: non-starting SPs (with game) OR any pitcher without a game
    # We only assign them to active slots if they are ALREADY in an active slot.
    # This prevents unnecessary benching, while avoiding pulling them off the bench.
    active_pitchers_secondary = [
        p for p in healthy_pitchers
        if _is_sp(p) and not p.get("is_starting_pitcher", False)
        and p.get("selected_position", "BN") not in ("BN", "IL", "IL+", "DL", "NA")
    ] + [
        p for p in no_game_pitchers
        if p.get("selected_position", "BN") not in ("BN", "IL", "IL+", "DL", "NA")
    ]
    for p in active_pitchers_secondary: p["_sort_priority"] = 1
    
    # We only assign primary pitchers (starters & relievers) to active slots.
    # Secondary pitchers (non-starting SPs) provide 0 stats and shouldn't fill slots.
    
    inactive_players = [
        p for p in roster
        if p.get("status", "") in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        or p.get("selected_position") == "NA"
    ]

    # Players with no game are handled separately (force-bench below),
    # EXCEPT for pitchers already in an active slot (who are now in active_pitchers_secondary)
    secondary_pitcher_ids = {p["player_id"] for p in active_pitchers_secondary}
    no_game_players = no_game_batters + [p for p in no_game_pitchers if p["player_id"] not in secondary_pitcher_ids]
    
    # Assign batters to batter slots
    batter_assignments = _assign_players_to_slots(active_batters, BATTER_SLOTS)
    
    # Assign pitchers to pitcher slots
    all_active_pitchers = active_pitchers_primary + active_pitchers_secondary
    pitcher_assignments = _assign_players_to_slots(all_active_pitchers, PITCHER_SLOTS)
    
    # Combine assignments
    all_assignments = {**batter_assignments, **pitcher_assignments}
    
    # Post-process: eliminate purely cosmetic swaps between active slots
    all_assignments = _remove_cosmetic_swaps(all_assignments, roster)
    
    # Determine which players are benched
    assigned_ids = set(all_assignments.keys())
    benched_batters = [p for p in active_batters if p["player_id"] not in assigned_ids]
    
    # All secondary pitchers that didn't fit (or were on the bench) are benched
    all_health_pitchers_considered = active_pitchers_primary + [
        p for p in pitchers
        if p.get("status", "") not in ("IL", "IL10", "IL15", "IL60", "DL", "IL-LT")
        and p.get("selected_position") != "NA"
        and not (p in active_pitchers_primary)
    ]
    benched_pitchers = [p for p in all_health_pitchers_considered if p["player_id"] not in assigned_ids]

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
    
    # Force-bench players with no game today
    for player in no_game_players:
        old_pos = player.get("selected_position", "BN")
        if old_pos != "BN" and old_pos not in ("IL", "IL+", "DL", "NA"):
            reason = "No game today"
            changes.append({
                "player_id": player["player_id"],
                "player_name": player["name"],
                "from": old_pos,
                "to": "BN",
                "reason": reason,
            })

    # Bench players that should be benched based on rankings
    for player in benched_batters + benched_pitchers:
        old_pos = player.get("selected_position", "BN")
        if old_pos != "BN" and old_pos not in ("IL", "IL+", "DL", "NA"):
            # Provide informative reason for non-starting SPs
            if _is_sp(player) and not player.get("is_starting_pitcher", False) and player.get("has_game", True):
                reason = player.get("ai_reasoning", "Not in starting rotation today")
            else:
                reason = player.get("ai_reasoning", "Lower ranked / no game")
            changes.append({
                "player_id": player["player_id"],
                "player_name": player["name"],
                "from": old_pos,
                "to": "BN",
                "reason": reason,
            })

    # Filter out cosmetic benching:
    # If a player is being benched, but their old active slot is still empty in the new lineup,
    # let them stay in their old slot to avoid unnecessary noise.
    from collections import Counter
    slot_capacity = Counter(s["slot"] for s in BATTER_SLOTS + PITCHER_SLOTS)
    slots_used = Counter(pos for pos in all_assignments.values())
    
    final_changes = []
    for change in changes:
        if change["to"] == "BN" and change["from"] not in ("IL", "IL+", "DL", "NA", "BN"):
            old_pos = change["from"]
            if slots_used[old_pos] < slot_capacity[old_pos]:
                # There's an empty slot here anyway, just leave them in it
                slots_used[old_pos] += 1
                continue
        final_changes.append(change)

    logger.info(f"Optimizer produced {len(final_changes)} lineup changes")
    return final_changes


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
            p.get("_sort_priority", 0),            # Primary pitchers (0) before secondary (1)
            len(p.get("eligible_positions", [])),  # Less positions = more specific
            p.get("ai_rank", 999),                 # Then by AI rank
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
    remaining_players.sort(key=lambda p: (p.get("_sort_priority", 0), p.get("ai_rank", 999)))
    
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


def _remove_cosmetic_swaps(assignments: dict, roster: list[dict]) -> dict:
    """
    Cancel out cosmetic slot swapping between players in active slots.
    If two active players can swap slots such that more players end up
    in the slot they were already in (their old_pos), make the swap.
    """
    def is_eligible(player, slot_name):
        if slot_name in ("Util", "P"):
            return True
        return slot_name in player.get("eligible_positions", [])

    improved = True
    while improved:
        improved = False
        pids = list(assignments.keys())
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                pid1 = pids[i]
                pid2 = pids[j]
                
                slot1 = assignments[pid1]
                slot2 = assignments[pid2]
                
                if slot1 == slot2:
                    continue
                    
                p1 = _find_player(roster, pid1)
                p2 = _find_player(roster, pid2)
                if not p1 or not p2:
                    continue
                
                old1 = p1.get("selected_position", "BN")
                old2 = p2.get("selected_position", "BN")
                
                # Current score (how many are in their old pos)
                current_score = (slot1 == old1) + (slot2 == old2)
                
                # If we swap them, are they eligible?
                if is_eligible(p1, slot2) and is_eligible(p2, slot1):
                    new_score = (slot2 == old1) + (slot1 == old2)
                    
                    if new_score > current_score:
                        # Swap improves the number of players staying in old_pos!
                        assignments[pid1] = slot2
                        assignments[pid2] = slot1
                        improved = True
                        break # break inner loop and restart
            if improved:
                break # break outer loop and restart
                
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
