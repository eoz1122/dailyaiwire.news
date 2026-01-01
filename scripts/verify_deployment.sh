#!/bin/bash

# Configuration
APP_DIR="/home/dailyai/dailyaiwire.news"
LOG_DIR="$APP_DIR/logs"
VENV_PIP="$APP_DIR/venv/bin/pip"

echo "==========================================="
echo "🔍 DailyAI Post-Deployment Verification"
echo "==========================================="
echo "Timestamp: $(date)"

# 1. Check Code Updates
echo ""
echo "[1] 📂 Checking Codebase Integrity..."
if grep -q "google-genai" "$APP_DIR/requirements.txt"; then
    echo "✅ requirements.txt uses google-genai"
else
    echo "❌ requirements.txt is OUTDATED"
fi

if grep -q "google.genai" "$APP_DIR/remove_duplicates.py"; then
    echo "✅ remove_duplicates.py uses google.genai"
else
    echo "❌ remove_duplicates.py is OUTDATED"
fi

# 2. Check Installed Packages
echo ""
echo "[2] 📦 Checking Python Dependencies..."
if $VENV_PIP freeze | grep -q "google-genai"; then
    echo "✅ google-genai library is installed"
else
    echo "❌ google-genai library is MISSING! Run: pip install -r requirements.txt"
fi

# 3. Check Service Status
echo ""
echo "[3] ⚙️ Checking Supervisor Services..."
sudo supervisorctl status

# 4. Check Scheduler Heartbeat
echo ""
echo "[4] 💓 Checking Tweet Scheduler Heartbeat..."
if [ -f "$LOG_DIR/twitter-access.log" ]; then
    # Look for Heartbeat in the last 20 lines
    if tail -n 20 "$LOG_DIR/twitter-access.log" | grep -q "Heartbeat"; then
        echo "✅ SUCCESS: Scheduler Heartbeat detected!"
        tail -n 5 "$LOG_DIR/twitter-access.log" | grep "Heartbeat"
    else
        echo "⚠️ WARNING: No Heartbeat found in recent logs."
        echo "   (If you just restarted, wait 60 seconds and try again)"
        echo "   Last 3 lines of output:"
        tail -n 3 "$LOG_DIR/twitter-access.log"
    fi
else
    echo "❌ Log file not found: $LOG_DIR/twitter-access.log"
fi

# 5. Check Errors
echo ""
echo "[5] 🚨 Checking Recent Errors..."
if [ -f "$LOG_DIR/twitter-error.log" ]; then
    ERR_COUNT=$(tail -n 20 "$LOG_DIR/twitter-error.log" | grep -v "DeprecationWarning" | grep "Error" | wc -l)
    if [ "$ERR_COUNT" -gt 0 ]; then
        echo "❌ Found $ERR_COUNT recent errors in twitter-error.log:"
        tail -n 20 "$LOG_DIR/twitter-error.log" | grep -v "DeprecationWarning" | grep "Error"
    else
        echo "✅ No critical errors found in recent log tail."
    fi
else
    echo "ℹ️ twitter-error.log not found."
fi

echo ""
echo "==========================================="
echo "✅ Verification Complete"
