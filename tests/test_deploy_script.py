import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy_to_vps.sh"


def test_deploy_script_exposes_fetcher_restart_option_only():
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--help"],
        capture_output=True,
        check=True,
        text=True,
    )

    assert "--with-fetcher" in result.stdout
    assert "--with-scheduler" not in result.stdout
    assert "tweet_scheduler" not in result.stdout


def test_deploy_script_restarts_web_service_through_systemd():
    script = DEPLOY_SCRIPT.read_text()

    assert 'SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-/usr/bin/systemctl}"' in script
    assert 'WEB_SERVICE="${WEB_SERVICE:-dailyaiwire-web.service}"' in script
    assert 'run_systemctl restart "$WEB_SERVICE"' in script
    assert 'run_systemctl status "$WEB_SERVICE"' in script


def test_deploy_script_keeps_fetcher_restart_explicit():
    script = DEPLOY_SCRIPT.read_text()

    assert "FETCHER_CHANGED=0" in script
    assert 'RESTART_FETCHER" -eq 1' in script
    assert "rerun with --with-fetcher" in script
