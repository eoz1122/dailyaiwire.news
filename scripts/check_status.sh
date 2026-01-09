#!/bin/bash

# Configuration
# Detect directory where script is located
APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
LOG_DIR="$APP_DIR/logs"

echo "======================================"
echo "    DailyAIWire Diagnostic Tool"
echo "======================================"
echo "Timestamp: $(date)"
echo ""

# 1. Check System Services
echo "[1] Checking System Services..."
if command -v supervisorctl &> /dev/null; then
    sudo supervisorctl status
else
    echo "⚠️ Supervisor not found."
fi
echo ""

# 2. Check Environment
echo "[2] Checking Environment..."
if [ -f "$APP_DIR/.env" ]; then
    echo "✅ .env file exists"
    
    # Check Google Creds
    if grep -q "GOOGLE_APPLICATION_CREDENTIALS" "$APP_DIR/.env"; then
        echo "✅ GOOGLE_APPLICATION_CREDENTIALS found in .env"
    else
        echo "❌ GOOGLE_APPLICATION_CREDENTIALS missing in .env (Required for Audio)"
    fi
    
    # Check DB
    if [ -f "$APP_DIR/news.db" ]; then
        DB_SIZE=$(du -h "$APP_DIR/news.db" | cut -f1)
        echo "✅ Database exists ($DB_SIZE)"
    else
        echo "❌ Database news.db missing!"
    fi
else
    echo "❌ .env file NOT FOUND at $APP_DIR/.env"
fi

# Check JSON Key existence (Dynamically from .env)
JSON_KEY_PATH=$(grep "GOOGLE_APPLICATION_CREDENTIALS" "$APP_DIR/.env" | cut -d '=' -f2 | tr -d '"' | tr -d "'")

if [ -n "$JSON_KEY_PATH" ] && [ -f "$JSON_KEY_PATH" ]; then
    echo "✅ Google Credentials file found at: $JSON_KEY_PATH"
elif [ -n "$JSON_KEY_PATH" ]; then
    echo "❌ Google Credentials file referenced in .env NOT FOUND at: $JSON_KEY_PATH"
else
    echo "❌ GOOGLE_APPLICATION_CREDENTIALS not set in .env"
fi
echo ""

# 3. Check Recent Logs
echo "[3] Latest Fetcher Activity (Last 10 lines)..."
if [ -f "$LOG_DIR/fetcher.log" ]; then
    tail -n 10 "$LOG_DIR/fetcher.log"
else
    echo "⚠️ Fetcher log not found."
fi
echo ""

echo "[4] Latest Web App Errors (Last 10 lines)..."
if [ -f "$LOG_DIR/gunicorn-error.log" ]; then
    tail -n 10 "$LOG_DIR/gunicorn-error.log"
else
    echo "⚠️ Gunicorn error log not found."
fi
echo ""

echo "[5] Latest Twitter Scheduler Logs (Last 10 lines)..."
if [ -f "$LOG_DIR/twitter-error.log" ]; then
    tail -n 10 "$LOG_DIR/twitter-error.log"
else
    echo "ℹ️ Twitter log not found (Service might not be active)."
fi

echo ""
echo "======================================"
echo "To run a manual test (best way to see errors):"
echo "cd $APP_DIR && source venv/bin/activate && python fetcher.py"
echo "======================================"
