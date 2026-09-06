# Yahoo Fantasy Baseball — Daily Lineup Optimizer 🏟️

Automatically sets optimal daily lineups for your Yahoo Fantasy Baseball Rotisserie league, powered by AI analysis and category-aware standings optimization.

## Features

- **🧠 AI-Powered Rankings** — Uses Gemini to analyze matchups, trends, and platoon advantages
- **📊 Category-Aware** — Identifies Roto point gaps and prioritizes stats that gain you standings points
- **🏥 IL Auto-Management** — Automatically moves injured players to IL and activates healthy ones
- **⚾ Smart Position Assignment** — Optimally assigns players to positions respecting eligibility rules
- **☁️ Cloud Ready** — Deploys to Google Cloud Run for daily automated execution

## Quick Start (Browser Automation — No Yahoo Developer API needed!)

Yahoo has largely shutdown or restricted personal developer apps on Yahoo Developer Network. This optimizer supports full browser automation via **Playwright**, which signs into your Yahoo Fantasy account directly.

### 1. Prerequisites

- Python 3.10+
- [Gemini API key](https://aistudio.google.com/) (free tier)

### 2. Install

```bash
cd yahoo-fantasy-optimizer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. One-Time Browser Login

Launch an interactive browser window to log into Yahoo (supports 2FA / passkey). Your session is saved securely in a local `.yahoo_browser_profile/`:

```bash
python -m src.main --browser-login --league-id YOUR_LEAGUE_ID
```

Log in with your Yahoo credentials. Once you see your fantasy league/team, return to your terminal and press `[Enter]`.

### 4. Daily Usage

```bash
# Preview changes (dry run with Gemini AI)
python -m src.main --browser --league-id 12345 --gemini-key YOUR_KEY

# Apply changes automatically via browser
python -m src.main --browser --league-id 12345 --gemini-key YOUR_KEY --apply

# Visible browser mode (watch Playwright make the clicks)
python -m src.main --browser --no-headless --league-id 12345 --gemini-key YOUR_KEY --apply

# Without AI (stat-based only)
python -m src.main --browser --league-id 12345 --no-ai --apply
```

### 5. Automated Daily Execution (macOS)

The optimizer is configured to run automatically every morning at **8:00 AM** via macOS `launchd`:

* **Runner script**: [`run_daily.sh`](file:///Users/khlin/Projects/yahoo-fantasy-optimizer/run_daily.sh)
* **LaunchAgent Plist**: `~/Library/LaunchAgents/com.khlin.yahoo-fantasy-optimizer.plist`
* **Log files**: [`daily_run.log`](file:///Users/khlin/Projects/yahoo-fantasy-optimizer/daily_run.log)

To manually start, stop, or check status:
```bash
# Check status
launchctl list | grep yahoo-fantasy-optimizer

# Stop schedule
launchctl unload ~/Library/LaunchAgents/com.khlin.yahoo-fantasy-optimizer.plist

# Re-enable schedule
launchctl load ~/Library/LaunchAgents/com.khlin.yahoo-fantasy-optimizer.plist
```

## CLI Options

| Flag | Description |
|---|---|
| `--browser` | Use Playwright browser automation (auto-selected if no OAuth credentials) |
| `--browser-login` | Open visible browser window to log into Yahoo once |
| `--no-headless` | Run browser in visible window so you can watch automated clicks |
| `--team-id ID` | Your Yahoo Fantasy team ID (optional, auto-detected) |
| `--apply` | Submit changes to Yahoo (default: dry-run) |
| `--date YYYY-MM-DD` | Optimize for a specific date |
| `--league-id ID` | Yahoo Fantasy league ID |
| `--team-name NAME` | Your team name (auto-detected) |
| `--gemini-key KEY` | Gemini API key |
| `--no-ai` | Use stat-based ranking only |
| `--debug` | Verbose logging |

You can also set environment variables: `YAHOO_LEAGUE_ID`, `GEMINI_API_KEY`, `YAHOO_TEAM_ID`, `YAHOO_TEAM_NAME`.

## Cloud Deployment (Google Cloud Run)

```bash
# Just run the deployment script!
# This automatically reads your .env and config/oauth2.json, creates a safe 
# temporary environment config, builds the image, and deploys to Cloud Run.
./deploy.sh
```

## League Configuration

This optimizer is configured for a **Rotisserie** league with:

- **Roster**: C, 1B, 2B, 3B, SS, OF×3, Util×2, SP×2, RP×2, P×4, BN×5, IL×3, NA
- **Batter Stats**: R, HR, RBI, SB, BB, TB, AVG
- **Pitcher Stats**: W, SV, K, ERA, WHIP, QS
