#!/bin/bash
# Deploy Yahoo Fantasy Optimizer to Google Cloud Run
set -e

PROJECT="alaska-award-search"
IMAGE="gcr.io/$PROJECT/yahoo-fantasy-optimizer"
JOB="yahoo-fantasy-optimizer"
REGION="us-central1"

echo "🏗️  Building and pushing Docker image..."
gcloud builds submit --tag $IMAGE

echo "⚙️  Generating environment variables..."
python3 -c "
import json
import os

env_vars = {}
try:
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env_vars[k] = v.strip('\"\'')
except FileNotFoundError:
    print('WARNING: .env not found!')

try:
    with open('config/oauth2.json', 'r') as f:
        env_vars['YAHOO_OAUTH_JSON'] = json.dumps(json.load(f))
except FileNotFoundError:
    print('WARNING: config/oauth2.json not found!')

with open('env_vars_temp.yaml', 'w') as f:
    json.dump(env_vars, f)
"

echo "🚀 Updating Cloud Run job..."
gcloud run jobs update $JOB --env-vars-file env_vars_temp.yaml --region $REGION

echo "🧹 Cleaning up..."
rm -f env_vars_temp.yaml

echo "✅ Deployment complete!"
