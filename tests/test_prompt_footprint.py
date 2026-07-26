import ai_config
from fetcher.ai_processor import build_article_analysis_prompt
import fetcher as fetcher_module


def test_system_instruction_stays_compact_enough_for_article_analysis():
    assert len(ai_config.get_system_instruction("Strategist")) < 2200


def test_article_analysis_prompt_footprint_stays_below_budget_for_three_article_batch():
    batch_input = []
    for idx in range(3):
        batch_input.append(
            f"ARTICLE ID: {idx}\n"
            f"SOURCE TITLE: Sample title {idx} (Ensure Output is English)\n"
            f"SOURCE CONTENT: {'A' * ai_config.ARTICLE_SOURCE_CHAR_LIMIT}"
        )

    prompt = build_article_analysis_prompt(batch_input)
    total_chars = len(prompt) + len(ai_config.get_system_instruction("Strategist"))

    assert ai_config.ARTICLE_SOURCE_CHAR_LIMIT <= 1400
    assert total_chars < 9000


def test_fetcher_batch_size_default_stays_at_three(monkeypatch):
    monkeypatch.delenv("FETCHER_BATCH_SIZE", raising=False)
    assert int(fetcher_module.os.getenv("FETCHER_BATCH_SIZE", "3")) == 3
