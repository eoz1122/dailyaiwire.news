import sqlite3
from types import SimpleNamespace

from fetcher import sources as src


def _new_cache_conn():
    conn = sqlite3.connect(":memory:")
    src._ensure_repo_quality_cache_schema(conn)
    return conn


def test_extract_github_repo_from_url():
    assert src._extract_github_repo("https://github.com/openai/openai-python") == ("openai", "openai-python")
    assert src._extract_github_repo("https://github.com/openai/openai-python/issues/123") == ("openai", "openai-python")


def test_extract_github_repo_ignores_non_repo_paths():
    assert src._extract_github_repo("https://github.com/topics/ai") is None
    assert src._extract_github_repo("https://example.com/openai/openai-python") is None


def test_github_quality_gate_rejects_below_min_stars_repo(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 10)
    monkeypatch.setattr(src, "_fetch_github_repo_stars_api", lambda owner, repo: 9)

    keep = src._passes_github_quality_gate("https://github.com/foo/bar", conn)
    assert keep is False

    row = conn.execute("SELECT stars FROM repo_quality_cache WHERE repo_key = 'foo/bar'").fetchone()
    assert row is not None
    assert row[0] == 9
    conn.close()


def test_github_quality_gate_allows_min_stars_repo(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 10)
    monkeypatch.setattr(src, "_fetch_github_repo_stars_api", lambda owner, repo: 10)
    assert src._passes_github_quality_gate("https://github.com/foo/bar", conn) is True
    conn.close()


def test_github_quality_gate_rejects_unknown_stars_repo(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 10)
    monkeypatch.setattr(src, "_fetch_github_repo_stars_api", lambda owner, repo: None)

    keep = src._passes_github_quality_gate("https://github.com/foo/bar", conn)

    assert keep is False
    row = conn.execute("SELECT stars FROM repo_quality_cache WHERE repo_key = 'foo/bar'").fetchone()
    assert row is None
    conn.close()


def test_github_quality_gate_uses_cache(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 10)
    calls = {"n": 0}

    def _fake_fetch(owner, repo):
        calls["n"] += 1
        return 12

    monkeypatch.setattr(src, "_fetch_github_repo_stars_api", _fake_fetch)
    assert src._passes_github_quality_gate("https://github.com/foo/bar", conn) is True
    assert calls["n"] == 1

    # Should use cache on second call and skip API.
    assert src._passes_github_quality_gate("https://github.com/foo/bar", conn) is True
    assert calls["n"] == 1
    conn.close()


def test_extract_huggingface_papers_from_html():
    html = """
    <html><body>
      <a href="/papers/2604.16044">Elucidating the SNR-t Bias of Diffusion Probabilistic Models</a>
      <a href="/papers/2604.16044">69</a>
      <a href="/papers/trending">Trending</a>
      <a href="/papers/2502.07408#community">Community</a>
      <a href="/papers/2502.07408">Maximal Brain Damage Without Data or Optimization</a>
    </body></html>
    """
    items = src._extract_huggingface_papers_from_html(html, max_items=10)
    assert [x["link"] for x in items] == [
        "https://huggingface.co/papers/2604.16044",
        "https://huggingface.co/papers/2502.07408",
    ]
    assert items[0]["source"] == "Hugging Face Papers"
    assert items[0]["title"].startswith("Elucidating the SNR-t Bias")


def test_repair_source_urls_updates_known_broken_feed():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sources (name TEXT, url TEXT)")
    conn.execute(
        "INSERT INTO sources (name, url) VALUES (?, ?)",
        ("Cambridge University AI", "https://www.cam.ac.uk/topics/artificial-intelligence/feed"),
    )
    conn.commit()

    repaired = src._repair_source_urls(
        conn,
        [("Cambridge University AI", "https://www.cam.ac.uk/topics/artificial-intelligence/feed")],
    )
    assert repaired == [("Cambridge University AI", "https://www.cam.ac.uk/taxonomy/term/51032/feed")]

    row = conn.execute("SELECT url FROM sources WHERE name = 'Cambridge University AI'").fetchone()
    assert row is not None
    assert row[0] == "https://www.cam.ac.uk/taxonomy/term/51032/feed"
    conn.close()


def test_normalize_source_url_maps_microsoft_research_feed():
    fixed = src._normalize_source_url(
        "Microsoft Research",
        "https://www.microsoft.com/en-us/research/feed/",
    )
    assert fixed == "https://azure.microsoft.com/en-us/blog/feed/"


def test_build_google_news_context_adds_publisher_and_wire_hint():
    entry = SimpleNamespace(
        summary=(
            '<a href="https://news.google.com/rss/articles/abc">Example title</a>'
            '&nbsp;&nbsp;<font color="#6f6f6f">Wired</font>'
        ),
        published="Sat, 25 Apr 2026 09:39:40 GMT",
        source={"href": "https://www.wired.com", "title": "Wired"},
    )
    context = src._build_google_news_context(entry, "AI Breakthrough Story", "Wired")

    assert "Headline: AI Breakthrough Story" in context
    assert "Publisher: Wired" in context
    assert "Publisher URL: https://www.wired.com" in context
    assert "Context: This came through Google News wire aggregation." in context
    assert len(context) > 120


def test_filter_high_signal_headlines_caps_results_to_dynamic_target(monkeypatch):
    class _FakeResponse:
        usage_metadata = SimpleNamespace(prompt_token_count=10, candidates_token_count=6)

    calls = []

    class _FakeGateway:
        def __init__(self, *args, **kwargs):
            calls.append({"model": kwargs.get("model_name") or args[0], "thinking": kwargs.get("thinking_budget")})

        def generate_text(self, *args, **kwargs):
            return ",".join(str(i) for i in range(16)), _FakeResponse()

    monkeypatch.setattr(src, "AIGateway", _FakeGateway)
    monkeypatch.setattr(src.ai_config, "ROUTINE_MODEL", "gemini-routine-test")
    monkeypatch.setattr(src.ai_config, "ROUTINE_THINKING_BUDGET", 0)
    monkeypatch.setattr(src.budget, "can_make_request", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(src.budget, "log_request", lambda *_args, **_kwargs: None)

    articles = [{"title": f"Test headline {i}"} for i in range(30)]
    # target_count for 30 headlines = min(16, max(8, 30//3)) = 10
    filtered = src.filter_high_signal_headlines(articles, recent_titles=[])
    assert len(filtered) == 10
    assert calls == [{"model": "gemini-routine-test", "thinking": 0}]
