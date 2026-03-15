# Yahoo Fantasy Baseball — Daily Lineup Optimizer 🏟️

Automatically sets optimal daily lineups for your Yahoo Fantasy Baseball Rotisserie league, powered by AI analysis and category-aware standings optimization.

## Features

- **🧠 AI-Powered Rankings** — Uses Gemini to analyze matchups, trends, and platoon advantages
- **📊 Category-Aware** — Identifies Roto point gaps and prioritizes stats that gain you standings points
- **🏥 IL Auto-Management** — Automatically moves injured players to IL and activates healthy ones
- **⚾ Smart Position Assignment** — Optimally assigns players to positions respecting eligibility rules
- **☁️ Cloud Ready** — Deploys to Google Cloud Run for daily automated execution

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Yahoo Developer App](https://developer.yahoo.com/apps/create/) (free)
- [Gemini API key](https://aistudio.google.com/) (free tier)

### 2. Install

```bash
cd yahoo-fantasy-optimizer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
# Copy the example config and fill in your Yahoo credentials
cp config/oauth2.json.example config/oauth2.json
# Edit config/oauth2.json with your Client ID and Client Secret
```

### 4. First Run (OAuth Setup)

```bash
# This will open a browser for Yahoo login (one-time)
python -m src.main --league-id YOUR_LEAGUE_ID --gemini-key YOUR_GEMINI_KEY
```

### 5. Daily Usage

```bash
# Preview changes (dry run)
python -m src.main --league-id 12345 --gemini-key YOUR_KEY

# Apply changes
python -m src.main --league-id 12345 --gemini-key YOUR_KEY --apply

# Without AI (stat-based only)
python -m src.main --league-id 12345 --no-ai --apply
```

## CLI Options

| Flag | Description |
|---|---|
| `--apply` | Submit changes to Yahoo (default: dry-run) |
| `--date YYYY-MM-DD` | Optimize for a specific date |
| `--league-id ID` | Yahoo Fantasy league ID |
| `--team-name NAME` | Your team name (auto-detected) |
| `--gemini-key KEY` | Gemini API key |
| `--no-ai` | Use stat-based ranking only |
| `--debug` | Verbose logging |

You can also set environment variables: `YAHOO_LEAGUE_ID`, `GEMINI_API_KEY`, `YAHOO_TEAM_NAME`.

## Cloud Deployment (Google Cloud Run)

```bash
# Build and push Docker image
gcloud builds submit --tag gcr.io/YOUR_PROJECT/fantasy-optimizer

# Create Cloud Run Job
gcloud run jobs create fantasy-optimizer \
  --image gcr.io/YOUR_PROJECT/fantasy-optimizer \
  --set-env-vars YAHOO_LEAGUE_ID=12345,GEMINI_API_KEY=your_key \
  --region us-west1

# Schedule daily at 9 AM PT
gcloud scheduler jobs create http fantasy-optimizer-daily \
  --schedule="0 9 * * *" \
  --time-zone="America/Los_Angeles" \
  --uri="https://us-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT/jobs/fantasy-optimizer:run" \
  --oauth-service-account-email=YOUR_SA@YOUR_PROJECT.iam.gserviceaccount.com
```

## League Configuration

This optimizer is configured for a **Rotisserie** league with:

- **Roster**: C, 1B, 2B, 3B, SS, OF×3, Util×2, SP×2, RP×2, P×4, BN×5, IL×3, NA
- **Batter Stats**: R, HR, RBI, SB, BB, TB, AVG
- **Pitcher Stats**: W, SV, K, ERA, WHIP, QS
