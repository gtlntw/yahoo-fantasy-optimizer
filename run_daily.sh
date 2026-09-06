#!/bin/bash
# Daily automated runner for Yahoo Fantasy Lineup Optimizer
# Runs at 8:00 AM daily

DIR="/Users/khlin/Projects/yahoo-fantasy-optimizer"
cd "$DIR"

# Ensure PATH includes Homebrew and standard binaries
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Log start timestamp
echo "=======================================================" >> "$DIR/daily_run.log"
echo "🚀 Starting Yahoo Fantasy Optimizer: $(date)" >> "$DIR/daily_run.log"
echo "=======================================================" >> "$DIR/daily_run.log"

# Run the optimizer:
# - Browser automation with headless Chromium
# - Applies lineup changes automatically (--apply)
# - Only makes suggestions for Free Agents (never auto-adds/drops)
# - Sends summary email to configured recipient
"$DIR/venv/bin/python" -m src.main \
  --browser \
  --headless \
  --apply \
  --league-id 14178 \
  --team-id 4 \
  >> "$DIR/daily_run.log" 2>&1

EXIT_CODE=$?
echo "🏁 Finished at $(date) with exit code: $EXIT_CODE" >> "$DIR/daily_run.log"
echo "" >> "$DIR/daily_run.log"
exit $EXIT_CODE
