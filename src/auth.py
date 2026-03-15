"""
Yahoo OAuth 2.0 authentication module.

Handles initial OAuth setup (browser-based login) and automatic
token refresh for subsequent runs.
"""

import json
import os
import logging
from pathlib import Path

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

logger = logging.getLogger(__name__)

DEFAULT_CREDS_FILE = Path(__file__).parent.parent / "config" / "oauth2.json"
# Store writable tokens in a local hidden folder instead of shared /tmp for better privacy
WRITABLE_CREDS_DIR = Path(__file__).parent.parent / ".yahoo_cache"
WRITABLE_CREDS_FILE = WRITABLE_CREDS_DIR / "oauth2.json"


def get_oauth(creds_file: str = None) -> OAuth2:
    """
    Get an authenticated OAuth2 session.
    
    Copies credentials to /tmp/yahoo-fantasy/oauth2.json
    since yahoo_oauth needs to write tokens back to the file.
    
    On first run, opens a browser for Yahoo login.
    On subsequent runs, uses saved tokens (auto-refreshes if expired).
    
    Args:
        creds_file: Path to oauth2.json credentials file.
                    Defaults to config/oauth2.json
    
    Returns:
        Authenticated OAuth2 session object
    """
    writable_path = _ensure_writable_creds(creds_file)

    logger.info("Authenticating with Yahoo OAuth...")
    oauth = OAuth2(None, None, from_file=str(writable_path))

    if not oauth.token_is_valid():
        logger.info("Token expired, refreshing...")
        oauth.refresh_access_token()

    logger.info("Authentication successful.")
    return oauth

def _ensure_writable_creds(creds_file: str = None) -> Path:
    """
    Ensure credentials exist in a writable location.
    
    If YAHOO_OAUTH_JSON env var exists (e.g. on Cloud Run), write it to temp.
    If /tmp/yahoo-fantasy/oauth2.json already exists with tokens,
    use it directly. Otherwise, copy from the project config dir.
    """
    WRITABLE_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Cloud Run / Headless support via Environment Variable
    env_json = os.environ.get("YAHOO_OAUTH_JSON")
    if env_json:
        try:
            # Validate it's JSON and write it
            json_blob = json.loads(env_json)
            with open(WRITABLE_CREDS_FILE, "w") as f:
                json.dump(json_blob, f)
            return WRITABLE_CREDS_FILE
        except json.JSONDecodeError as e:
            error_msg = f"YAHOO_OAUTH_JSON environment variable is not valid JSON! Error: {e}"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
    # If writable copy already exists with tokens, use it
    if WRITABLE_CREDS_FILE.exists():
        with open(WRITABLE_CREDS_FILE) as f:
            existing = json.load(f)
        if existing.get("consumer_key") and existing.get("consumer_key") != "YOUR_CLIENT_ID_HERE":
            logger.debug(f"Using existing credentials from {WRITABLE_CREDS_FILE}")
            return WRITABLE_CREDS_FILE
    
    # Otherwise, copy from project config
    source_path = Path(creds_file) if creds_file else DEFAULT_CREDS_FILE
    
    try:
        with open(source_path) as f:
            creds = json.load(f)
    except (FileNotFoundError, PermissionError):
        raise FileNotFoundError(
            f"Credentials file not found or not readable: {source_path}\n"
            f"Copy config/oauth2.json.example to config/oauth2.json and fill in "
            f"your Client ID and Client Secret from https://developer.yahoo.com/apps/"
        )
    
    if creds.get("consumer_key") == "YOUR_CLIENT_ID_HERE":
        raise ValueError(
            "Please update config/oauth2.json with your actual Yahoo Developer "
            "Client ID and Client Secret."
        )
    
    # Write to writable location
    with open(WRITABLE_CREDS_FILE, "w") as f:
        json.dump(creds, f, indent=2)
    
    logger.info(f"Credentials copied to {WRITABLE_CREDS_FILE}")
    return WRITABLE_CREDS_FILE


def get_league(oauth: OAuth2, league_id: str, game_code: str = "mlb") -> yfa.League:
    """
    Get a Yahoo Fantasy League object.
    
    Args:
        oauth: Authenticated OAuth2 session
        league_id: Yahoo Fantasy league ID (e.g., "12345")
        game_code: Sport code, default "mlb"
    
    Returns:
        yahoo_fantasy_api League object
    """
    gm = yfa.Game(oauth, game_code)
    
    # Get the league IDs for the current season
    league_ids = gm.league_ids(year=2026)
    
    # Build the full league key
    full_league_id = None
    for lid in league_ids:
        if league_id in lid:
            full_league_id = lid
            break
    
    if not full_league_id:
        # Try constructing it manually
        game_id = gm.game_id()
        full_league_id = f"{game_id}.l.{league_id}"
        logger.warning(
            f"League ID {league_id} not found in your leagues. "
            f"Trying constructed key: {full_league_id}"
        )
    
    logger.info(f"Connected to league: {full_league_id}")
    return gm.to_league(full_league_id)


def get_team(oauth: OAuth2, league: yfa.League, team_name: str = None) -> yfa.Team:
    """
    Get your team from the league.
    
    Args:
        oauth: Authenticated OAuth2 session
        league: Yahoo Fantasy League object
        team_name: Your team name. If None, uses the first team owned by you.
    
    Returns:
        yahoo_fantasy_api Team object
    """
    teams = league.teams()
    
    if team_name:
        for team_key, team_info in teams.items():
            if team_info["name"].lower() == team_name.lower():
                logger.info(f"Found team: {team_info['name']}")
                return league.to_team(team_key)
        raise ValueError(f"Team '{team_name}' not found in league.")
    
    # If no team name specified, let the yfa API find our team
    try:
        team_key = league.team_key()
        if team_key:
            # We need to get the team name to log it properly
            for tk, team_info in teams.items():
                if tk == team_key:
                    logger.info(f"Using auto-detected team: {team_info['name']} (key: {team_key})")
                    return league.to_team(team_key)
            
            # Fallback if name not found in teams list
            logger.info(f"Using auto-detected team key: {team_key}")
            return league.to_team(team_key)
    except Exception as e:
        logger.debug(f"Could not auto-detect team: {e}")
    
    raise ValueError("Could not find your team in the league. Try specifying --team-name.")
