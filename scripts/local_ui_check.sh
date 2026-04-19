#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8010}"
ROUTE="${1:-/}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${OUT_DIR:-/tmp/dailyaiwire-local-ui-check-$STAMP}"
SERVER_LOG="$OUT_DIR/server.log"
BASE_URL="http://${HOST}:${PORT}${ROUTE}"
CHROME_APP="/Applications/Google Chrome.app"
CHROME_BIN="$CHROME_APP/Contents/MacOS/Google Chrome"
SERVER_PID=""

mkdir -p "$OUT_DIR"

cleanup() {
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "Missing Python virtualenv at $ROOT_DIR/.venv/bin/python" >&2
    exit 1
fi

if [[ ! -d "$CHROME_APP" ]] || [[ ! -x "$CHROME_BIN" ]]; then
    echo "Google Chrome is not installed at $CHROME_APP" >&2
    exit 1
fi

if lsof -ti "tcp:${PORT}" >/dev/null 2>&1; then
    echo "Using existing local server on port $PORT"
else
    echo "Starting local server on ${HOST}:${PORT}"
    "$ROOT_DIR/.venv/bin/python" -c "from app import app; app.run(host='${HOST}', port=${PORT}, debug=False)" \
        >"$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
fi

echo "Waiting for ${BASE_URL}"
for _ in {1..30}; do
    if curl -fsS "$BASE_URL" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -fsS "$BASE_URL" >/dev/null 2>&1; then
    echo "Local server did not become ready. Check $SERVER_LOG" >&2
    exit 1
fi

echo "Opening Chrome windows"
osascript <<OSA >/dev/null
tell application "Google Chrome"
    activate

    set desktopWindow to make new window
    set URL of active tab of desktopWindow to "${BASE_URL}"
    set bounds of desktopWindow to {40, 60, 1520, 1180}

    set mobileWindow to make new window
    set URL of active tab of mobileWindow to "${BASE_URL}"
    set bounds of mobileWindow to {80, 80, 520, 1080}
end tell
OSA

sleep 2

DESKTOP_SHOT="$OUT_DIR/desktop$(echo "$ROUTE" | tr '/' '_' | sed 's/^_$/_home/')".png
MOBILE_SHOT="$OUT_DIR/mobile$(echo "$ROUTE" | tr '/' '_' | sed 's/^_$/_home/')".png

echo "Capturing screenshots"
"$CHROME_BIN" \
    --headless=new \
    --disable-gpu \
    --disable-features=LazyImageLoading,LazyFrameLoading \
    --hide-scrollbars \
    --virtual-time-budget=5000 \
    --window-size=1440,2200 \
    --screenshot="$DESKTOP_SHOT" \
    "$BASE_URL" >/dev/null 2>&1

"$CHROME_BIN" \
    --headless=new \
    --disable-gpu \
    --disable-features=LazyImageLoading,LazyFrameLoading \
    --hide-scrollbars \
    --virtual-time-budget=5000 \
    --window-size=390,2200 \
    --screenshot="$MOBILE_SHOT" \
    "$BASE_URL" >/dev/null 2>&1

echo "Desktop screenshot: $DESKTOP_SHOT"
echo "Mobile screenshot:  $MOBILE_SHOT"
echo "Server log:         $SERVER_LOG"
