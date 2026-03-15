"""
Category-Aware Standings Analysis for Roto leagues.

Analyzes your position in each scoring category relative to other teams
and identifies categories where small stat gains could earn Roto points.
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CategoryPriority(Enum):
    """Priority level for a scoring category."""
    HIGH = "HIGH"        # Within striking distance of gaining a Roto point
    MEDIUM = "MEDIUM"    # Moderate gap, maintain pace
    LOW = "LOW"          # Large lead or insurmountable gap
    PROTECT = "PROTECT"  # Leading in a rate stat that could slip


@dataclass
class CategoryGap:
    """Analysis of a single scoring category."""
    category: str
    your_value: float
    your_rank: int          # 1-indexed (1 = best)
    your_roto_points: int   # Roto points for this cat
    gap_to_gain: float      # How much more to gain +1 roto point
    gap_to_lose: float      # How much you'd need to lose to drop -1 roto point
    team_ahead_value: float # Value of the team just ahead
    team_behind_value: float  # Value of the team just behind
    priority: CategoryPriority
    is_rate_stat: bool

    def __str__(self):
        emoji = {
            CategoryPriority.HIGH: "🔴",
            CategoryPriority.MEDIUM: "🟡",
            CategoryPriority.LOW: "🟢",
            CategoryPriority.PROTECT: "⚠️",
        }[self.priority]
        
        if self.priority == CategoryPriority.HIGH:
            return (f"{emoji} {self.category}: {self.your_value:.3f} "
                    f"(#{self.your_rank}, need {self.gap_to_gain:+.3f} for +1 pt)")
        elif self.priority == CategoryPriority.PROTECT:
            return (f"{emoji} {self.category}: {self.your_value:.3f} "
                    f"(#{self.your_rank}, protect — {self.gap_to_lose:+.3f} buffer)")
        else:
            return (f"{emoji} {self.category}: {self.your_value:.3f} "
                    f"(#{self.your_rank})")


# Define which stats are rate stats (lower is better for ERA/WHIP)
RATE_STATS = {"AVG", "ERA", "WHIP"}
LOWER_IS_BETTER = {"ERA", "WHIP"}

# Roto scoring categories for this league
BATTER_CATEGORIES = ["R", "HR", "RBI", "SB", "BB", "TB", "AVG"]
PITCHER_CATEGORIES = ["W", "SV", "K", "ERA", "WHIP", "QS"]
ALL_CATEGORIES = BATTER_CATEGORIES + PITCHER_CATEGORIES

# Thresholds for priority classification
# "Close" means within this percentage of the gap to the next team
HIGH_PRIORITY_THRESHOLD = 0.15   # Within 15% of catching next team
MEDIUM_PRIORITY_THRESHOLD = 0.40  # Within 40%


def analyze_standings(standings: list[dict], my_team_key: str) -> list[CategoryGap]:
    """
    Analyze current Roto standings and produce category gap analysis.
    
    Args:
        standings: League standings data from Yahoo API
        my_team_key: Your team's key identifier
    
    Returns:
        List of CategoryGap objects, one per scoring category
    """
    num_teams = len(standings)
    gaps = []
    
    for category in ALL_CATEGORIES:
        is_rate = category in RATE_STATS
        lower_better = category in LOWER_IS_BETTER
        
        # Extract each team's value for this category
        team_values = []
        for team_data in standings:
            team_key = team_data.get("team_key", "")
            team_name = team_data.get("name", "Unknown")
            
            # Get the stat value from team standings
            stat_value = _extract_stat(team_data, category)
            team_values.append({
                "team_key": team_key,
                "name": team_name,
                "value": stat_value,
            })
        
        # Sort: for counting stats, higher is better; for ERA/WHIP, lower is better
        team_values.sort(
            key=lambda x: x["value"],
            reverse=not lower_better
        )
        
        # Find my team's position
        my_rank = None
        my_value = 0.0
        for i, tv in enumerate(team_values):
            if tv["team_key"] == my_team_key:
                my_rank = i + 1  # 1-indexed
                my_value = tv["value"]
                break
        
        if my_rank is None:
            logger.warning(f"Could not find your team in standings for {category}")
            continue
        
        # Roto points: best team gets num_teams points, worst gets 1
        my_roto_points = num_teams - my_rank + 1
        
        # Gap to gain: difference to team ranked one spot better
        if my_rank > 1:
            team_ahead = team_values[my_rank - 2]  # 0-indexed
            gap_to_gain = abs(team_ahead["value"] - my_value)
            team_ahead_value = team_ahead["value"]
        else:
            gap_to_gain = 0.0
            team_ahead_value = my_value
        
        # Gap to lose: difference to team ranked one spot worse
        if my_rank < num_teams:
            team_behind = team_values[my_rank]  # 0-indexed  
            gap_to_lose = abs(my_value - team_behind["value"])
            team_behind_value = team_behind["value"]
        else:
            gap_to_lose = float("inf")
            team_behind_value = my_value
        
        # Determine priority
        priority = _determine_priority(
            category=category,
            my_rank=my_rank,
            num_teams=num_teams,
            gap_to_gain=gap_to_gain,
            gap_to_lose=gap_to_lose,
            my_value=my_value,
            is_rate=is_rate,
            lower_better=lower_better,
        )
        
        gap = CategoryGap(
            category=category,
            your_value=my_value,
            your_rank=my_rank,
            your_roto_points=my_roto_points,
            gap_to_gain=gap_to_gain,
            gap_to_lose=gap_to_lose,
            team_ahead_value=team_ahead_value,
            team_behind_value=team_behind_value,
            priority=priority,
            is_rate_stat=is_rate,
        )
        gaps.append(gap)
        logger.debug(str(gap))
    
    return gaps


def build_priority_context(gaps: list[CategoryGap]) -> str:
    """
    Build a human-readable priority context string for the AI ranker.
    
    Args:
        gaps: List of CategoryGap objects from analyze_standings()
    
    Returns:
        Formatted string describing category priorities
    """
    lines = ["Category Priority Analysis (Roto Standings):"]
    lines.append(f"{'Category':<8} {'Value':>8} {'Rank':>5} {'Gap to +1pt':>12} {'Priority':<10}")
    lines.append("-" * 50)
    
    for gap in sorted(gaps, key=lambda g: _priority_sort_key(g.priority)):
        gap_str = f"{gap.gap_to_gain:+.3f}" if gap.your_rank > 1 else "  (1st)"
        lines.append(
            f"{gap.category:<8} {gap.your_value:>8.3f} "
            f"{'#' + str(gap.your_rank):>5} {gap_str:>12} "
            f"{gap.priority.value:<10}"
        )
    
    return "\n".join(lines)


def get_category_weights(gaps: list[CategoryGap]) -> dict[str, float]:
    """
    Convert category gaps into numerical weights for player ranking.
    
    Players who contribute to HIGH priority categories get boosted.
    
    Args:
        gaps: List of CategoryGap objects
    
    Returns:
        Dict mapping category name -> weight multiplier (0.5 to 2.0)
    """
    weights = {}
    for gap in gaps:
        if gap.priority == CategoryPriority.HIGH:
            weights[gap.category] = 2.0
        elif gap.priority == CategoryPriority.PROTECT:
            # For rate stats we're protecting, weight slightly higher
            # to be careful about who we start
            weights[gap.category] = 1.5
        elif gap.priority == CategoryPriority.MEDIUM:
            weights[gap.category] = 1.0
        else:  # LOW
            weights[gap.category] = 0.5
    
    return weights


def _determine_priority(
    category: str,
    my_rank: int,
    num_teams: int,
    gap_to_gain: float,
    gap_to_lose: float,
    my_value: float,
    is_rate: bool,
    lower_better: bool,
) -> CategoryPriority:
    """Determine the priority level for a category."""
    
    # Already in 1st place in this category
    if my_rank == 1:
        if is_rate and gap_to_lose < _small_gap_threshold(category, my_value):
            return CategoryPriority.PROTECT
        return CategoryPriority.LOW  # Already winning, maintain
    
    # In last place with large gap
    if my_rank == num_teams and gap_to_gain > _large_gap_threshold(category, my_value):
        return CategoryPriority.LOW  # Punt category
    
    # Check if we're close to gaining a point
    # Case: Everyone is at 0.0 (pre-season or missing stats), don't mark as HIGH priority
    if my_value == 0 and gap_to_gain == 0 and (gap_to_lose == 0 or gap_to_lose == float("inf")):
        return CategoryPriority.MEDIUM
        
    if gap_to_gain <= _small_gap_threshold(category, my_value):
        return CategoryPriority.HIGH
    
    # Protecting a rate stat where we're close to losing
    if is_rate and my_rank <= 3 and gap_to_lose < _small_gap_threshold(category, my_value):
        return CategoryPriority.PROTECT
    
    # Check medium threshold
    if gap_to_gain <= _medium_gap_threshold(category, my_value):
        return CategoryPriority.MEDIUM
    
    return CategoryPriority.LOW


def _small_gap_threshold(category: str, value: float) -> float:
    """What counts as a 'small' gap for a category (within striking distance)."""
    thresholds = {
        # Batting counting stats: ~1 week of production
        "R": 8, "HR": 3, "RBI": 8, "SB": 3, "BB": 6, "TB": 15,
        # Batting rate stat
        "AVG": 0.005,
        # Pitching counting stats
        "W": 2, "SV": 3, "K": 15, "QS": 2,
        # Pitching rate stats
        "ERA": 0.15, "WHIP": 0.020,
    }
    return thresholds.get(category, 5)


def _medium_gap_threshold(category: str, value: float) -> float:
    """What counts as a 'medium' gap (reachable over a few weeks)."""
    thresholds = {
        "R": 20, "HR": 8, "RBI": 20, "SB": 8, "BB": 15, "TB": 40,
        "AVG": 0.012,
        "W": 5, "SV": 8, "K": 40, "QS": 5,
        "ERA": 0.35, "WHIP": 0.045,
    }
    return thresholds.get(category, 15)


def _large_gap_threshold(category: str, value: float) -> float:
    """What counts as a 'large' gap (likely unpuntable)."""
    return _medium_gap_threshold(category, value) * 2.5


def _extract_stat(team_data: dict, category: str) -> float:
    """Extract a stat value from team standings data."""
    # The Yahoo API standings format varies; handle common structures
    stats = team_data.get("stats", {})
    
    # Detect missing stats entirely (pre-season)
    if not stats:
        return 0.0
        
    # Try direct key lookup
    if category in stats:
        return float(stats[category])
    
    # Try lowercase
    if category.lower() in stats:
        return float(stats[category.lower()])
    
    # Try in a nested stats list
    if isinstance(stats, list):
        for stat in stats:
            if stat.get("name") == category or stat.get("abbr") == category:
                return float(stat.get("value", 0))
    
    logger.warning(f"Could not find stat '{category}' in standings data")
    return 0.0


def _priority_sort_key(priority: CategoryPriority) -> int:
    """Sort key for displaying priorities (HIGH first)."""
    order = {
        CategoryPriority.HIGH: 0,
        CategoryPriority.PROTECT: 1,
        CategoryPriority.MEDIUM: 2,
        CategoryPriority.LOW: 3,
    }
    return order.get(priority, 4)
