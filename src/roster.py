"""
Roster submission module.

Submits optimized lineup changes to Yahoo Fantasy via the API.
"""

import datetime
import logging
from typing import Optional

import yahoo_fantasy_api as yfa

logger = logging.getLogger(__name__)


def submit_changes(
    team: yfa.Team,
    changes: list[dict],
    date: Optional[datetime.date] = None,
    dry_run: bool = True,
) -> bool:
    """
    Submit lineup changes to Yahoo Fantasy.
    
    Args:
        team: Yahoo Fantasy Team object
        changes: List of change dicts from optimizer.optimize_lineup()
        date: Date for the changes. Defaults to today.
        dry_run: If True, only log changes without submitting.
    
    Returns:
        True if changes were submitted (or no changes needed), False on error
    """
    if date is None:
        date = datetime.date.today()
    
    if not changes:
        logger.info("No changes to submit.")
        return True
    
    if dry_run:
        logger.info(f"DRY RUN: Would submit {len(changes)} changes for {date}")
        for change in changes:
            logger.info(
                f"  {change['player_name']}: "
                f"{change['from']} → {change['to']}"
            )
        return True
    
    # Build the modified lineup for the API
    modified_lineup = []
    for change in changes:
        modified_lineup.append({
            "player_id": change["player_id"],
            "selected_position": change["to"],
        })
    
    try:
        logger.info(f"Submitting {len(modified_lineup)} position changes for {date}...")
        team.change_positions(date, modified_lineup)
        logger.info("✅ Lineup changes submitted successfully!")
        
        for change in changes:
            logger.info(
                f"  ✅ {change['player_name']}: "
                f"{change['from']} → {change['to']}"
            )
        
        return True
        
    except RuntimeError as e:
        logger.error(f"❌ Failed to submit lineup changes: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error submitting changes: {e}")
        return False

def format_browser_instructions(
    changes: list[dict],
    league_id: str,
    team_id: str,
    date: datetime.date
) -> str:
    """
    Format lineup changes as a prompt for an AI Browser Agent.
    """
    if not changes:
        return "No roster changes are needed for today."
        
    url = f"https://baseball.fantasysports.yahoo.com/b1/{league_id}/{team_id}"
    
    prompt = (
        f"Go to the Yahoo Fantasy Baseball team page: {url}\n"
        f"Make sure you are viewing the roster for {date.strftime('%b %-d')}.\n\n"
        "Please execute the following roster moves. Look for the player's name, "
        "click the button showing their current position next to their name, "
        "then click the button for their new target position to swap them or move them.\n\n"
        "Required Moves:\n"
    )
    
    for i, change in enumerate(changes, 1):
        prompt += (
            f"{i}. Player: {change['player_name']}\n"
            f"   Current Position: {change['from']}\n"
            f"   Target Position: {change['to']}\n\n"
        )
        
    prompt += (
        "After making all these moves, click the 'Save Changes' button if it appears "
        "(sometimes Yahoo auto-saves, but check to be sure). Verify that the roster matches "
        "these target positions."
    )
    
    return prompt
