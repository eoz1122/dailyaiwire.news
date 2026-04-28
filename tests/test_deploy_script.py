import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy_to_vps.sh"


def test_deploy_script_exposes_scheduler_restart_option():
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--help"],
        capture_output=True,
        check=True,
        text=True,
    )

    assert "--with-scheduler" in result.stdout
    assert "tweet_scheduler" in result.stdout


def test_deploy_script_auto_restarts_scheduler_for_social_posting_changes():
    script = DEPLOY_SCRIPT.read_text()

    assert "SCHEDULER_CHANGED" in script
    assert "restart_scheduler" in script
    assert "tweet_scheduler\\.py|social_distributor\\.py|url_shortener\\.py|requirements\\.txt" in script


def test_deploy_script_scheduler_pid_matcher_requires_python_process():
    script = DEPLOY_SCRIPT.read_text()

    assert '$2 ~ /^python/' in script
