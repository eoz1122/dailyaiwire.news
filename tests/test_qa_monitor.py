from types import SimpleNamespace

import qa_monitor


def _response(html, status_code=200):
    return SimpleNamespace(status_code=status_code, content=html.encode("utf-8"))


def test_current_article_markup_passes_qa(monkeypatch):
    html = """
    <html><body>
      <h1>Current article headline</h1>
      <section data-article-summary-tone="adaptive">
        <p class="genui-reading-kicker">A useful signal summary.</p>
      </section>
      <div data-article-source-link="prominent">
        <a href="https://example.com/source">Read Article at Source</a>
      </div>
    </body></html>
    """
    monkeypatch.setattr(qa_monitor.requests, "get", lambda *args, **kwargs: _response(html))

    assert qa_monitor.run_post_publication_audit("https://dailyaiwire.news/article/test") is True


def test_qa_rejects_empty_current_summary(monkeypatch):
    html = """
    <html><body>
      <h1>Current article headline</h1>
      <section data-article-summary-tone="adaptive"><p></p></section>
      <div data-article-source-link="prominent">
        <a href="https://example.com/source">Read Article at Source</a>
      </div>
    </body></html>
    """
    monkeypatch.setattr(qa_monitor.requests, "get", lambda *args, **kwargs: _response(html))

    assert qa_monitor.run_post_publication_audit("https://dailyaiwire.news/article/test") is False


def test_qa_rejects_missing_source_cta(monkeypatch):
    html = """
    <html><body>
      <h1>Current article headline</h1>
      <section data-article-summary-tone="adaptive">
        <p class="genui-reading-kicker">A useful signal summary.</p>
      </section>
    </body></html>
    """
    monkeypatch.setattr(qa_monitor.requests, "get", lambda *args, **kwargs: _response(html))

    assert qa_monitor.run_post_publication_audit("https://dailyaiwire.news/article/test") is False


def test_legacy_article_labels_remain_supported(monkeypatch):
    html = """
    <html><body>
      <h1>Legacy article headline</h1>
      <h2>The Gist</h2><p>Legacy summary.</p>
      <a href="https://example.com/source">Read Full Story</a>
    </body></html>
    """
    monkeypatch.setattr(qa_monitor.requests, "get", lambda *args, **kwargs: _response(html))

    assert qa_monitor.run_post_publication_audit("https://dailyaiwire.news/article/test") is True
