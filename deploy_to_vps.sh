#!/usr/bin/env bash
# Deployment script for DailyAIWire.news production.
# Intended to run on the VPS or be streamed over SSH from CI.

set -euo pipefail

APP_DIR="${APP_DIR:-/home/dailyai/dailyaiwire.news}"
REMOTE="${REMOTE:-origin}"
TARGET_REF="${TARGET_REF:-origin/main}"
RESTART_FETCHER=0
RESTART_SCHEDULER=0
ALLOW_RESET=0
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
MAX_HEALTH_ATTEMPTS="${MAX_HEALTH_ATTEMPTS:-20}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-2}"
SUPERVISORCTL_BIN="${SUPERVISORCTL_BIN:-/usr/bin/supervisorctl}"
SUDO_BIN="${SUDO_BIN:-/usr/bin/sudo}"
SUPERVISOR_ACCESS_MODE=""

usage() {
    cat <<'EOF'
Usage: deploy_to_vps.sh [options]

Options:
  --ref <git-ref>         Deploy an exact ref or commit SHA. Default: origin/main
  --with-fetcher          Restart dailyaiwire_fetcher after the app deploy
  --with-scheduler        Restart tweet_scheduler after the app deploy
  --allow-reset           Allow non-fast-forward reset to the target ref
  --app-dir <path>        Override the application directory
  --health-url <url>      Override the health check URL
  -h, --help              Show this help text

Examples:
  ./deploy_to_vps.sh
  ./deploy_to_vps.sh --ref aa6bd17
  ./deploy_to_vps.sh --ref aa6bd17 --with-fetcher
  ./deploy_to_vps.sh --ref aa6bd17 --with-scheduler
  ./deploy_to_vps.sh --ref 200556e --allow-reset
EOF
}

log() {
    printf '[deploy] %s\n' "$*"
}

fail() {
    printf '[deploy] ERROR: %s\n' "$*" >&2
    exit 1
}

run() {
    log "+ $*"
    "$@"
}

detect_supervisor_access() {
    if "$SUPERVISORCTL_BIN" status dailyaiwire >/dev/null 2>&1; then
        SUPERVISOR_ACCESS_MODE="direct"
        return
    fi

    if "$SUDO_BIN" -n "$SUPERVISORCTL_BIN" status dailyaiwire >/dev/null 2>&1; then
        SUPERVISOR_ACCESS_MODE="sudo"
        return
    fi

    fail "Cannot control Supervisor as $(whoami). Grant NOPASSWD sudo for '$SUPERVISORCTL_BIN restart dailyaiwire', '$SUPERVISORCTL_BIN status dailyaiwire', '$SUPERVISORCTL_BIN restart dailyaiwire_fetcher', '$SUPERVISORCTL_BIN status dailyaiwire_fetcher', '$SUPERVISORCTL_BIN restart tweet_scheduler', and '$SUPERVISORCTL_BIN status tweet_scheduler', or run the deploy as a user with direct Supervisor access."
}

try_supervisor() {
    local action="$1"
    local program="$2"

    case "$SUPERVISOR_ACCESS_MODE" in
        direct)
            "$SUPERVISORCTL_BIN" "$action" "$program"
            ;;
        sudo)
            "$SUDO_BIN" -n "$SUPERVISORCTL_BIN" "$action" "$program"
            ;;
        *)
            fail "Supervisor access mode is not initialized."
            ;;
    esac
}

run_supervisor() {
    local action="$1"
    local program="$2"

    log "+ supervisorctl $action $program"
    try_supervisor "$action" "$program"
}

scheduler_pids() {
    ps -u "$(whoami)" -o pid= -o args= \
        | awk -v python_path="$APP_DIR/venv/bin/python" \
            'index($0, python_path) && index($0, "tweet_scheduler.py") { print $1 }'
}

restart_scheduler() {
    if try_supervisor restart tweet_scheduler >/dev/null 2>&1; then
        log "+ supervisorctl restart tweet_scheduler"
        return
    fi

    log "Supervisor restart unavailable for tweet_scheduler. Falling back to TERM on the owned scheduler process."
    local pids
    pids="$(scheduler_pids)"
    [[ -n "$pids" ]] || fail "tweet_scheduler is not controllable and no owned scheduler process was found."

    log "+ kill -TERM $pids"
    kill -TERM $pids
    sleep 5

    if try_supervisor status tweet_scheduler >/dev/null 2>&1; then
        log "+ supervisorctl status tweet_scheduler"
        return
    fi

    pids="$(scheduler_pids)"
    [[ -n "$pids" ]] || fail "tweet_scheduler did not restart after TERM fallback."
    log "tweet_scheduler is running after TERM fallback: $pids"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ref)
            [[ $# -ge 2 ]] || fail "--ref requires a value"
            TARGET_REF="$2"
            shift 2
            ;;
        --with-fetcher)
            RESTART_FETCHER=1
            shift
            ;;
        --with-scheduler)
            RESTART_SCHEDULER=1
            shift
            ;;
        --allow-reset)
            ALLOW_RESET=1
            shift
            ;;
        --app-dir)
            [[ $# -ge 2 ]] || fail "--app-dir requires a value"
            APP_DIR="$2"
            shift 2
            ;;
        --health-url)
            [[ $# -ge 2 ]] || fail "--health-url requires a value"
            HEALTH_URL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done

[[ -d "$APP_DIR/.git" ]] || fail "Not a git repository: $APP_DIR"
cd "$APP_DIR"

if ! git diff --quiet || ! git diff --cached --quiet; then
    git status --short --branch >&2 || true
    fail "Tracked local changes detected in $APP_DIR. Refusing to deploy."
fi

detect_supervisor_access

PREVIOUS_SHA="$(git rev-parse HEAD)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

log "Starting deploy from $PREVIOUS_SHA on branch $CURRENT_BRANCH"
run git fetch --prune "$REMOTE"

TARGET_SHA="$(git rev-parse --verify "${TARGET_REF}^{commit}")" || fail "Cannot resolve target ref: $TARGET_REF"
log "Target ref resolved to $TARGET_SHA"

if [[ "$CURRENT_BRANCH" != "main" ]]; then
    run git checkout main
fi

FETCHER_CHANGED=0
if git diff --name-only "$PREVIOUS_SHA" "$TARGET_SHA" | grep -Eq '^(fetcher\.py|fetcher/|social_distributor\.py|audio_generator\.py|remove_duplicates\.py|requirements\.txt)$'; then
    FETCHER_CHANGED=1
fi

SCHEDULER_CHANGED=0
if git diff --name-only "$PREVIOUS_SHA" "$TARGET_SHA" | grep -Eq '^(tweet_scheduler\.py|social_distributor\.py|url_shortener\.py|requirements\.txt)$'; then
    SCHEDULER_CHANGED=1
fi

if [[ "$PREVIOUS_SHA" != "$TARGET_SHA" ]]; then
    if git merge-base --is-ancestor "$PREVIOUS_SHA" "$TARGET_SHA"; then
        run git merge --ff-only "$TARGET_SHA"
    else
        [[ "$ALLOW_RESET" -eq 1 ]] || fail "Target $TARGET_SHA is not a fast-forward from $PREVIOUS_SHA. Re-run with --allow-reset for an intentional rollback/reset."
        log "Non-fast-forward deploy approved. Resetting main to $TARGET_SHA"
        run git reset --hard "$TARGET_SHA"
    fi
else
    log "Repository already at target SHA"
fi

run bash -lc 'source venv/bin/activate && pip install --disable-pip-version-check -r requirements.txt --quiet'

run_supervisor restart dailyaiwire

if [[ "$RESTART_FETCHER" -eq 1 ]]; then
    run_supervisor restart dailyaiwire_fetcher
elif [[ "$FETCHER_CHANGED" -eq 1 ]]; then
    log "Fetcher-related files changed, but fetcher restart was skipped by design."
    log "If this deploy needs the new fetcher code, rerun with --with-fetcher."
fi

if [[ "$RESTART_SCHEDULER" -eq 1 || "$SCHEDULER_CHANGED" -eq 1 ]]; then
    restart_scheduler
fi

run_supervisor status dailyaiwire
if [[ "$RESTART_FETCHER" -eq 1 ]]; then
    run_supervisor status dailyaiwire_fetcher
fi
if [[ "$RESTART_SCHEDULER" -eq 1 || "$SCHEDULER_CHANGED" -eq 1 ]]; then
    if ! try_supervisor status tweet_scheduler; then
        pids="$(scheduler_pids)"
        [[ -n "$pids" ]] || fail "tweet_scheduler status check failed and no owned scheduler process was found."
        log "tweet_scheduler process check passed: $pids"
    fi
fi

attempt=1
health_ok=0
while [[ "$attempt" -le "$MAX_HEALTH_ATTEMPTS" ]]; do
    if HEALTH_RESPONSE="$(curl -fsS "$HEALTH_URL")"; then
        health_ok=1
        break
    fi
    sleep "$HEALTH_SLEEP_SECONDS"
    attempt=$((attempt + 1))
done

[[ "$health_ok" -eq 1 ]] || fail "Health check failed at $HEALTH_URL after $MAX_HEALTH_ATTEMPTS attempts."

ROLLBACK_FETCHER_FLAG=""
if [[ "$RESTART_FETCHER" -eq 1 ]]; then
    ROLLBACK_FETCHER_FLAG=" --with-fetcher"
fi

ROLLBACK_SCHEDULER_FLAG=""
if [[ "$RESTART_SCHEDULER" -eq 1 || "$SCHEDULER_CHANGED" -eq 1 ]]; then
    ROLLBACK_SCHEDULER_FLAG=" --with-scheduler"
fi

log "Health check passed: $HEALTH_RESPONSE"
log "Deploy complete."
log "Rollback command:"
log "  ./deploy_to_vps.sh --ref $PREVIOUS_SHA --allow-reset${ROLLBACK_FETCHER_FLAG}${ROLLBACK_SCHEDULER_FLAG}"
