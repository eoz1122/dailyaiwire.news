from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR_PATH = ROOT / "ops/n8n/linkedin-select-diverse.js"
SUCCESS_PATH = ROOT / "ops/n8n/linkedin-mark-success-diverse.js"
README_PATH = ROOT / "ops/n8n/README.md"
GITIGNORE_PATH = ROOT / ".gitignore"


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


def test_generated_workflow_contract_uses_versioned_source_scripts():
    readme = README_PATH.read_text()
    gitignore = GITIGNORE_PATH.read_text()

    assert "`linkedin-select-diverse.js`" in readme
    assert "`linkedin-mark-success-diverse.js`" in readme
    assert "outputs/linkedin-n8n/linkedin-rss-scheduled-24-daily.json" in readme
    assert "/outputs/" in gitignore
