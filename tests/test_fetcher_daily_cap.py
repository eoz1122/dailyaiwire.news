from datetime import date


def test_count_analyzed_articles_today_sums_article_ids(monkeypatch):
    import db as db_module
    import fetcher as fetcher_module

    conn = db_module.get_db_connection()
    try:
        conn.execute(
            "INSERT INTO ai_logs (timestamp, model, prompt_type, prompt_text, response_text, cost_estimate) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "2026-06-07 08:00:00",
                "gemini-2.5-flash",
                "article_analysis",
                "ARTICLE ID: 0\n...\nARTICLE ID: 1\n...\nARTICLE ID: 2",
                "[]",
                0.0,
            ),
        )
        conn.execute(
            "INSERT INTO ai_logs (timestamp, model, prompt_type, prompt_text, response_text, cost_estimate) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "2026-06-07 10:00:00",
                "gemini-2.5-flash",
                "article_analysis",
                "ARTICLE ID: 0\n...\nARTICLE ID: 1",
                "[]",
                0.0,
            ),
        )
        conn.execute(
            "INSERT INTO ai_logs (timestamp, model, prompt_type, prompt_text, response_text, cost_estimate) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "2026-06-06 23:00:00",
                "gemini-2.5-flash",
                "article_analysis",
                "ARTICLE ID: 0\n...\nARTICLE ID: 1\n...\nARTICLE ID: 2\n...\nARTICLE ID: 3",
                "[]",
                0.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    counted = fetcher_module._count_analyzed_articles_for_day(date(2026, 6, 7))

    assert counted == 5


def test_limit_articles_for_cycle_respects_remaining_daily_budget():
    import fetcher as fetcher_module

    articles = [{"title": f"Article {i}"} for i in range(12)]

    limited = fetcher_module._limit_articles_for_cycle(
        articles,
        per_cycle_cap=12,
        daily_cap=30,
        analyzed_today=25,
    )

    assert len(limited) == 5


def test_limit_articles_for_cycle_returns_empty_when_daily_cap_exhausted():
    import fetcher as fetcher_module

    articles = [{"title": f"Article {i}"} for i in range(12)]

    limited = fetcher_module._limit_articles_for_cycle(
        articles,
        per_cycle_cap=12,
        daily_cap=30,
        analyzed_today=30,
    )

    assert limited == []
