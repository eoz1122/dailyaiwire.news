import sqlite3

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


def test_github_quality_gate_rejects_zero_star_repo(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 1)
    monkeypatch.setattr(src, "_fetch_github_repo_stars_api", lambda owner, repo: 0)

    keep = src._passes_github_quality_gate("https://github.com/foo/bar", conn)
    assert keep is False

    row = conn.execute("SELECT stars FROM repo_quality_cache WHERE repo_key = 'foo/bar'").fetchone()
    assert row is not None
    assert row[0] == 0
    conn.close()


def test_github_quality_gate_allows_nonzero_star_repo(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 1)
    monkeypatch.setattr(src, "_fetch_github_repo_stars_api", lambda owner, repo: 1)
    assert src._passes_github_quality_gate("https://github.com/foo/bar", conn) is True
    conn.close()


def test_github_quality_gate_uses_cache(monkeypatch):
    conn = _new_cache_conn()
    monkeypatch.setattr(src, "GITHUB_MIN_STARS", 1)
    calls = {"n": 0}

    def _fake_fetch(owner, repo):
        calls["n"] += 1
        return 7

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
