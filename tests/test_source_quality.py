import sqlite3
from datetime import datetime
from types import SimpleNamespace

from fetcher import sources as src
from services.story_dedup import canonical_research_paper_id


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


def test_extract_huggingface_papers_defaults_to_four_candidates():
    html = "<html><body>" + "".join(
        f'<a href="/papers/2607.{paper_id:05d}">Research Paper {paper_id}</a>'
        for paper_id in range(6)
    ) + "</body></html>"

    items = src._extract_huggingface_papers_from_html(html)

    assert len(items) == 4


def test_canonical_research_paper_id_matches_arxiv_and_hugging_face_versions():
    assert canonical_research_paper_id("https://arxiv.org/abs/2607.07820v2") == "arxiv:2607.07820"
    assert canonical_research_paper_id("https://arxiv.org/pdf/2607.07820.pdf") == "arxiv:2607.07820"
    assert canonical_research_paper_id("https://huggingface.co/papers/2607.07820") == "arxiv:2607.07820"
    assert canonical_research_paper_id("https://example.com/papers/2607.07820") is None


def test_known_article_link_blocks_cross_source_research_paper():
    existing_urls = {"https://arxiv.org/abs/2607.07820"}
    known_research_ids = {
        canonical_research_paper_id(url)
        for url in existing_urls
        if canonical_research_paper_id(url)
    }

    assert src._is_known_article_link(
        "https://huggingface.co/papers/2607.07820",
        {},
        existing_urls,
        known_research_ids,
    ) is True


def test_known_article_link_blocks_cross_source_paper_already_in_current_batch():
    unique_articles = {
        "https://arxiv.org/abs/2607.07820": {
            "link": "https://arxiv.org/abs/2607.07820",
        }
    }
    known_research_ids = {"arxiv:2607.07820"}

    assert src._is_known_article_link(
        "https://huggingface.co/papers/2607.07820",
        unique_articles,
        set(),
        known_research_ids,
    ) is True


def test_extract_meta_blog_posts_from_html():
    html = """
    <html><body>
      <div class="card">
        <a href="https://ai.meta.com/blog/genesis-mission/" aria-label="Read How Meta Powers Genesis"></a>
        <a href="https://ai.meta.com/blog/genesis-mission/">How Meta Powers Genesis</a>
        <span>Jul 21, 2026</span>
      </div>
      <div class="card">
        <a href="/blog/muse-image-video/">FEATURED</a>
        <a href="/blog/muse-image-video/">Introducing Muse Image and Video</a>
        <span>July 7, 2026</span>
      </div>
      <a href="/blog/">Blog index</a>
    </body></html>
    """

    items = src._extract_meta_blog_posts_from_html(html, max_items=10)

    assert [item["link"] for item in items] == [
        "https://ai.meta.com/blog/genesis-mission/",
        "https://ai.meta.com/blog/muse-image-video/",
    ]
    assert items[0]["title"] == "How Meta Powers Genesis"
    assert items[0]["published"] == "2026-07-21T00:00:00"
    assert items[1]["title"] == "Introducing Muse Image and Video"
    assert items[1]["published"] == "2026-07-07T00:00:00"
    assert all(item["source"] == "Meta AI" for item in items)


def test_recent_meta_blog_posts_excludes_stale_backfill():
    items = [
        {"title": "Current", "published": "2026-07-21T00:00:00"},
        {"title": "Still recent", "published": "2026-06-29T00:00:00"},
        {"title": "Stale", "published": "2026-04-08T00:00:00"},
    ]

    recent = src._recent_meta_blog_posts(
        items,
        now=datetime(2026, 7, 21, 12, 0, 0),
        recency_days=45,
    )

    assert [item["title"] for item in recent] == ["Current", "Still recent"]


def test_extract_meta_article_context_keeps_models_and_measured_outcomes():
    html = """
    <html><body>
      <p>Lawrence Berkeley National Laboratory operates advanced scientific facilities that generate large amounts of experimental data.</p>
      <p>Background details describe historical detector upgrades and manual analysis constraints across several departments.</p>
      <p>At the heart of SYNAPS-I are two open-source foundation models released by Meta: Segment Anything Model 3 (SAM 3) and DINOv3.</p>
      <p>The team fine-tuned both models on scientific imaging data and deployed them across 300 A100 GPUs.</p>
      <p>What previously required a month of expert annotation per time step now takes 15 minutes.</p>
      <p>Meta's open-source approach allows the models to run inside secure government infrastructure.</p>
      <p>Subscribe to our newsletter to keep up with Meta AI models, events, and research.</p>
    </body></html>
    """

    context = src._extract_meta_article_context(
        html,
        "How Meta's AI Models Power Genesis Mission Projects",
        max_chars=600,
    )

    assert len(context) <= 600
    assert "SAM 3" in context
    assert "DINOv3" in context
    assert "300 A100 GPUs" in context
    assert "15 minutes" in context
    assert "Subscribe to our newsletter" not in context


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
        "https://azure.microsoft.com/en-us/blog/feed/",
    )
    assert fixed == "https://www.microsoft.com/en-us/research/feed/"


def test_normalize_source_url_maps_deprecated_meta_feed_to_blog():
    fixed = src._normalize_source_url(
        "Meta AI (FAIR)",
        "https://research.facebook.com/feed/",
    )

    assert fixed == "https://ai.meta.com/blog/"
    assert "Meta AI (FAIR)" in src._SPECIAL_SOURCE_HANDLERS


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

    articles = [{"title": f"Test headline {i}"} for i in range(24)]
    # target_count for 24 headlines = min(12, max(8, 24//4)) = 8
    filtered = src.filter_high_signal_headlines(articles, recent_titles=[])
    assert len(filtered) == 8
    assert calls == [{"model": "gemini-routine-test", "thinking": 0}]


def test_filter_high_signal_headlines_prefilters_low_signal_titles(monkeypatch):
    seen_prompt = {"value": ""}

    class _FakeResponse:
        usage_metadata = SimpleNamespace(prompt_token_count=10, candidates_token_count=6)

    class _FakeGateway:
        def __init__(self, *args, **kwargs):
            pass

        def generate_text(self, prompt, *args, **kwargs):
            seen_prompt["value"] = prompt
            return "0,1,2,3,4,5", _FakeResponse()

    monkeypatch.setattr(src, "AIGateway", _FakeGateway)
    monkeypatch.setattr(src.ai_config, "ROUTINE_MODEL", "gemini-routine-test")
    monkeypatch.setattr(src.ai_config, "ROUTINE_THINKING_BUDGET", 0)
    monkeypatch.setattr(src.budget, "can_make_request", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(src.budget, "log_request", lambda *_args, **_kwargs: None)

    articles = [
        {"title": "OpenAI releases new benchmark for reasoning agents", "source": "OpenAI"},
        {"title": "NVIDIA launches new inference chip for AI workloads", "source": "NVIDIA"},
        {"title": "Anthropic research paper improves alignment auditing", "source": "Anthropic"},
        {"title": "EU regulation targets frontier AI reporting", "source": "Reuters"},
        {"title": "Open source robotics model expands household tasks", "source": "Hugging Face"},
        {"title": "Meta security paper reveals jailbreak mitigation", "source": "Meta"},
        {"title": "Top AI SEO tools for marketers in 2026", "source": "PR Newswire"},
        {"title": "How to use AI for landing page copy", "source": "Business Wire"},
        {"title": "All-in-one AI assistant for sales teams launches", "source": "GlobeNewswire"},
        {"title": "Sponsored: best AI productivity app discount", "source": "AccessWire"},
        {"title": "Chrome extension brings AI meeting notes", "source": "PR Newswire"},
        {"title": "Guide to choosing an AI CRM for teams", "source": "Business Wire"},
    ]

    filtered = src.filter_high_signal_headlines(articles, recent_titles=[])

    assert len(filtered) == 6
    assert "Top AI SEO tools for marketers in 2026" not in seen_prompt["value"]
    assert "Sponsored: best AI productivity app discount" not in seen_prompt["value"]
    assert all("marketers" not in article["title"].lower() for article in filtered)


def test_build_headline_filter_prompt_caps_recent_titles_and_avoids_duplicate_headlines(monkeypatch):
    monkeypatch.setattr(src, "HEADLINE_FILTER_RECENT_TITLES_LIMIT", 3)

    candidate_articles = [
        {"title": "OpenAI releases enterprise agent benchmark"},
        {"title": "NVIDIA expands inference stack for Europe"},
    ]
    recent_titles = [
        "Old title one",
        "Old title two",
        "Old title three",
        "Old title four",
        "Old title five",
    ]

    prompt = src._build_headline_filter_prompt(candidate_articles, recent_titles, target_count=2)

    assert "Old title one" in prompt
    assert "Old title two" in prompt
    assert "Old title three" in prompt
    assert "Old title four" not in prompt
    assert "Old title five" not in prompt
    assert prompt.count("0: OpenAI releases enterprise agent benchmark") == 1
    assert prompt.count("1: NVIDIA expands inference stack for Europe") == 1
    assert "Example Input" not in prompt
    assert "HEADLINES:" not in prompt


def test_recent_title_guard_blocks_cross_source_rewording():
    candidate = "Hugging Face Confirms AI Agent-Driven Security Breach"
    published = "Hugging Face Network Breached by Autonomous AI Agent"

    assert src._is_duplicate_of_recent_title(candidate, published) is True


def test_recent_title_guard_keeps_distinct_model_versions():
    assert src._is_duplicate_of_recent_title(
        "OpenAI Launches GPT-6 Reasoning Model",
        "OpenAI Launches GPT-5 Reasoning Model",
    ) is False
