import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "outputs/linkedin-n8n/linkedin-rss-scheduled-24-daily.json"
SELECTOR_PATH = ROOT / "ops/n8n/linkedin-select-diverse.js"
SUCCESS_PATH = ROOT / "ops/n8n/linkedin-mark-success-diverse.js"


def _node_code(workflow, name):
    return next(
        node["parameters"]["jsCode"]
        for node in workflow["nodes"]
        if node["name"] == name
    )


def test_linkedin_rss_exposes_diversity_metadata(client):
    response = client.get("/rss/linkedin")

    assert response.status_code == 200
    assert b"<category>source:" in response.data
    assert b"<category>research:" in response.data


def test_linkedin_workflow_enforces_daily_diversity_caps():
    selector = SELECTOR_PATH.read_text()
    success = SUCCESS_PATH.read_text()

    assert "DAILY_RESEARCH_LIMIT = 6" in selector
    assert "DAILY_SOURCE_LIMIT = 4" in selector
    assert "DAILY_CATEGORY_LIMIT = 6" in selector
    assert "dailyResearchPosts" in selector
    assert "dailySourceCounts" in selector
    assert "dailyCategoryCounts" in selector
    assert "dailyResearchPosts" in success
    assert "dailySourceCounts" in success
    assert "dailyCategoryCounts" in success


def test_linkedin_success_counter_is_idempotent():
    success = SUCCESS_PATH.read_text()

    assert "const alreadyProcessed = staticData.processedIds.includes(articleId);" in success
    assert "if (!alreadyProcessed) {" in success


def test_importable_workflow_contains_reviewed_diversity_scripts():
    workflow = json.loads(WORKFLOW_PATH.read_text())

    assert _node_code(workflow, "Select Next Article") == SELECTOR_PATH.read_text()
    assert _node_code(workflow, "Mark Successfully Posted") == SUCCESS_PATH.read_text()
