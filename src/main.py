"""
Yahoo Fantasy Baseball Daily Lineup Optimizer — CLI Entry Point.

Usage:
  python -m src.main                      # Dry-run (preview changes)
  python -m src.main --apply              # Submit lineup to Yahoo
  python -m src.main --date 2026-04-15    # Optimize specific date
  python -m src.main --no-ai              # Skip AI, use stat-based ranking
  python -m src.main --debug              # Verbose logging
"""

import argparse
import datetime
import logging
import os
import sys

from dotenv import load_dotenv
from . import auth, data, ai_ranker, standings, il_manager, optimizer, roster, notifier

# Load environment variables from .env file (if it exists)
load_dotenv()

logger = logging.getLogger("yahoo-fantasy-optimizer")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Yahoo Fantasy Baseball Daily Lineup Optimizer"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Submit changes to Yahoo (default: dry-run only)",
    )
    parser.add_argument(
        "--browser-apply",
        action="store_true",
        help="Generate an automation prompt for an AI Browser Subagent instead of using API",
    )
    parser.add_argument(
        "--email-to",
        type=str,
        default=os.environ.get("NOTIFICATION_EMAIL", ""),
        help="Email address to send the daily lineup suggestions to",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to optimize for (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--league-id",
        type=str,
        default=os.environ.get("YAHOO_LEAGUE_ID", ""),
        help="Yahoo Fantasy league ID (or set YAHOO_LEAGUE_ID env var)",
    )
    parser.add_argument(
        "--team-name",
        type=str,
        default=os.environ.get("YAHOO_TEAM_NAME", ""),
        help="Your team name (optional, auto-detected if not set)",
    )
    parser.add_argument(
        "--creds-file",
        type=str,
        default=None,
        help="Path to oauth2.json credentials file",
    )
    parser.add_argument(
        "--gemini-key",
        type=str,
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="Gemini API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI ranking, use stat-based fallback only",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Parse date
    if args.date:
        target_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.date.today()
    
    dry_run = not args.apply and not args.browser_apply
    
    # Header
    print()
    print("🏟️  Yahoo Fantasy Baseball Lineup Optimizer")
    print(f"📅  Date: {target_date}")
    if args.browser_apply:
        print("🔧  Mode: 🤖 BROWSER AUTOMATION (generating prompt)")
    elif args.apply:
        print("🔧  Mode: 🔴 LIVE (applying changes via API)")
    else:
        print("🔧  Mode: 🟢 DRY RUN (preview only)")
    print("=" * 55)
    print()
    
    # Validate inputs
    if not args.league_id:
        print("❌ League ID required. Use --league-id or set YAHOO_LEAGUE_ID env var.")
        print("   Find it in your league URL: baseball.fantasysports.yahoo.com/b1/XXXXX")
        sys.exit(1)
    
    try:
        # ── Step 1: Authenticate ──────────────────────────────────
        print("🔑 Authenticating with Yahoo...")
        oauth = auth.get_oauth(args.creds_file)
        league = auth.get_league(oauth, args.league_id)
        team = auth.get_team(oauth, league, args.team_name or None)
        print("   ✅ Connected!")
        print()
        
        # ── Step 2: Fetch roster ──────────────────────────────────
        print("📋 Fetching roster...")
        current_roster = data.get_roster(team, target_date)
        print(f"   Found {len(current_roster)} players")
        print()
        
        # ── Step 3: Analyze standings ─────────────────────────────
        print("📊 Analyzing category standings...")
        league_standings = data.get_standings(league)
        
        # Find our team key
        team_details = team.details() if hasattr(team, 'details') else {}
        my_team_key = team_details.get("team_key", "")
        
        # If we can't get teamkey from details, try to find it
        if not my_team_key:
            for t in league_standings:
                # First team as fallback
                my_team_key = t.get("team_key", "")
                break
        
        category_gaps = standings.analyze_standings(league_standings, my_team_key)
        
        # Display category analysis
        print()
        print(standings.build_priority_context(category_gaps))
        print()
        
        # ── Step 4: IL Management ─────────────────────────────────
        print("🏥 Checking IL management...")
        il_moves = il_manager.manage_il(team, current_roster, target_date, dry_run=dry_run)
        print(il_manager.format_il_moves(il_moves))
        print()
        
        # If IL moves were applied, refetch the roster
        if il_moves and not dry_run:
            print("   Refetching roster after IL moves...")
            current_roster = data.get_roster(team, target_date)
        
        # ── Step 5: Rank players ──────────────────────────────────
        if args.no_ai or not args.gemini_key:
            if not args.no_ai and not args.gemini_key:
                print("⚠️  No Gemini API key provided. Using stat-based ranking.")
                print("   Set --gemini-key or GEMINI_API_KEY for AI-powered ranking.")
            else:
                print("📈 Using stat-based ranking (--no-ai mode)...")
            
            ranked_roster = ai_ranker.fallback_ranking(
                [p for p in current_roster if p.get("position_type") == "B"]
            ) + ai_ranker.fallback_ranking(
                [p for p in current_roster if p.get("position_type") == "P"]
            )
        else:
            print("🧠 AI ranking players with Gemini...")
            ai_ranker.configure_gemini(args.gemini_key)
            ranked_roster = ai_ranker.rank_players(
                current_roster,
                category_gaps,
                str(target_date),
            )
        
        # Show rankings
        print()
        print("Player Rankings:")
        for p in ranked_roster:
            rank = p.get("ai_rank", "?")
            reason = p.get("ai_reasoning", "")
            reason_str = f" — {reason}" if reason else ""
            print(f"  #{rank:<3} {p['name']:25s} ({p.get('position_type', '?')}){reason_str}")
        print()
        
        # ── Step 6: Optimize lineup ───────────────────────────────
        print("⚾ Optimizing lineup...")
        changes = optimizer.optimize_lineup(ranked_roster)
        print(optimizer.format_changes(changes))
        print()
        
        # ── Step 7: Submit changes ────────────────────────────────
        if changes:
            print(f"📝 Total changes: {len(changes)} lineup + {len(il_moves)} IL")
            print()
            
            if dry_run:
                print("🟢 DRY RUN — no changes submitted.")
                print("   Run with --apply to submit these changes to Yahoo via API.")
                print("   Run with --browser-apply to generate a prompt for an AI browser assistant.")
            elif args.browser_apply:
                print("🤖 Generating instruction prompt for Browser Automation...")
                team_details = team.details() if hasattr(team, 'details') else {}
                league_id = str(league.league_id)
                team_id = my_team_key.split('.t.')[-1] if '.t.' in my_team_key else "1"
                
                prompt = roster.format_browser_instructions(changes, league_id, team_id, target_date)
                print("\n" + "=" * 60)
                print("COPY THE TEXT BELOW AND PASTE IT TO YOUR AI BROWSER ASSISTANT")
                print("=" * 60 + "\n")
                print(prompt)
                print("\n" + "=" * 60)
            else:
                success = roster.submit_changes(team, changes, target_date, dry_run=False)
                if success:
                    print("🎉 All changes submitted successfully!")
                else:
                    print("❌ Some changes failed. Check logs above.")
                    sys.exit(1)
            
            # ── Email Notification ────────────────────────────────────
            if args.email_to:
                print(f"📧 Formatting email notification for {args.email_to}...")
                subject = f"⚾ Yahoo Fantasy Basebal Optimizer: {len(changes)} Moves Needed for {target_date}"
                
                body = (
                    f"Date: {target_date}\n"
                    f"Team: {args.team_name or 'Auto-Detected'}\n"
                    f"League ID: {args.league_id}\n\n"
                    "Suggested Lineup Changes:\n"
                    "--------------------------\n"
                )
                
                for change in changes:
                    body += f"• {change['player_name']}: {change['from']} → {change['to']}\n"
                    if "reason" in change and change["reason"]:
                        body += f"  Rationale: {change['reason']}\n"
                    body += "\n"
                    
                body += "\n"
                if il_moves:
                    body += f"IL Moves ({len(il_moves)}):\n"
                    for move in il_moves:
                        body += f"• {move['player_name']}: {move['from']} → {move['to']}\n"
                
                body += f"\nYahoo Fantasy URL: https://baseball.fantasysports.yahoo.com/b1/{args.league_id}\n"
                
                notifier.send_email(subject, body, args.email_to)
                
        else:
            print("✅ Lineup is already optimal! No changes needed.")
            
            if args.email_to:
                subject = f"⚾ Yahoo Fantasy Baseball Optimizer: No Moves Needed for {target_date}"
                body = "Your lineup is already perfectly optimized for today! No moves are required."
                notifier.send_email(subject, body, args.email_to)
        
        print()
        
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error")
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
