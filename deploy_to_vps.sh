#!/bin/bash
# Deployment script for DailyAIWire.news VPS
# Run this on the VPS at 72.62.95.46

set -e  # Exit on error

echo "🚀 Starting deployment..."

# Navigate to project directory
cd /home/dailyai/dailyaiwire.news

# Pull latest changes
echo "📥 Pulling latest changes from Git..."
git fetch origin
git checkout main
git pull origin main

# Install/update dependencies if requirements.txt changed
echo "📦 Checking dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

# Restart the application using supervisor
echo "🔄 Restarting application..."
sudo supervisorctl restart dailyaiwire

# Check status
echo "✅ Checking application status..."
sudo supervisorctl status dailyaiwire

echo "🎉 Deployment complete!"
