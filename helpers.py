"""
Shared template filters and utility functions — DailyAIWire.news
Extracted from app.py during Blueprint refactoring.
"""
import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from markupsafe import Markup


def slugify(text):
    """Simple slugify for editorial titles."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


def remove_emojis(text):
    """Remove emoji characters from text."""
    if not text:
        return ""
    return re.sub(r'[\U00010000-\U0010ffff]', '', text)


def time_ago(dt_str):
    """Convert a datetime string to a human-readable 'X ago' format."""
    if not dt_str:
        return ""
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            try:
                dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(dt_str, '%Y-%m-%d')

        # Database timestamps are stored in UTC; treat naive values as UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 0:
            return "Future"
        if seconds < 60:
            return "Just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        if seconds < 604800:
            return f"{seconds // 86400}d ago"
        if seconds < 2592000:
            return f"{seconds // 604800}w ago"
        if seconds < 31536000:
            return f"{seconds // 2592000}mo ago"
        return f"{seconds // 31536000}y ago"
    except Exception:
        return dt_str


def add_utm_to_html(html_content):
    """Add UTM parameters to all links in HTML content."""
    if not html_content:
        return ""

    def replacer(match):
        url = match.group(1)
        if 'utm_source=dailyaiwire' in url:
            return f'href="{url}"'

        separator = '&' if '?' in url else '?'
        new_url = f"{url}{separator}utm_source=dailyaiwire&utm_medium=smart_referral"
        return f'href="{new_url}"'

    pattern = r'href=["\'](.*?)["\']'
    return re.sub(pattern, replacer, html_content)


def register_filters(app):
    """Register all custom Jinja2 template filters on the Flask app."""
    app.jinja_env.filters['time_ago'] = time_ago
    app.jinja_env.filters['remove_emojis'] = remove_emojis
    app.template_filter('add_utm_to_html')(add_utm_to_html)


def clean_markdown(text):
    """Strip common markdown formatting for plain-text social posts."""
    if not text:
        return ""
    return text.replace('**', '').replace('__', '').replace('~~', '')


def format_plaintext_html(text):
    """Escape untrusted text and preserve line breaks for safe HTML rendering."""
    escaped = html.escape(text or "")
    return Markup(escaped.replace("\n", "<br>"))


class _HTMLAllowlistSanitizer(HTMLParser):
    """Very small HTML sanitizer for admin preview fragments."""

    ALLOWED_TAGS = {"br", "p", "strong", "em", "b", "i", "ul", "ol", "li", "a"}
    ALLOWED_ATTRS = {"a": {"href", "title", "target", "rel"}}
    SKIP_CONTENT_TAGS = {"script", "style"}
    ALLOWED_SCHEMES = {"http", "https", "mailto"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_CONTENT_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth or tag not in self.ALLOWED_TAGS:
            return

        safe_attrs = []
        for key, value in attrs:
            if key not in self.ALLOWED_ATTRS.get(tag, set()):
                continue
            if value is None:
                continue
            cleaned = self._sanitize_attr(tag, key, value)
            if cleaned is None:
                continue
            safe_attrs.append(f' {key}="{html.escape(cleaned, quote=True)}"')

        self.parts.append(f"<{tag}{''.join(safe_attrs)}>")

    def handle_endtag(self, tag):
        if tag in self.SKIP_CONTENT_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth or tag not in self.ALLOWED_TAGS or tag == "br":
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.parts.append(html.escape(data))

    def handle_entityref(self, name):
        if self.skip_depth:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if self.skip_depth:
            return
        self.parts.append(f"&#{name};")

    def _sanitize_attr(self, tag, key, value):
        if tag == "a" and key == "href":
            parsed = urlparse(value.strip())
            if parsed.scheme and parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
                return None
        return value


def sanitize_preview_html(html_fragment):
    """Sanitize a limited HTML fragment for same-origin admin preview rendering."""
    sanitizer = _HTMLAllowlistSanitizer()
    sanitizer.feed(html_fragment or "")
    sanitizer.close()
    return Markup("".join(sanitizer.parts))


class _PlainTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")
        elif tag in {"p", "div", "li"}:
            if self.parts and not self.parts[-1].endswith("\n"):
                self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li"}:
            if self.parts and not self.parts[-1].endswith("\n"):
                self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_plaintext(html_fragment):
    """Convert a small HTML fragment into readable plain text."""
    parser = _PlainTextExtractor()
    parser.feed(html_fragment or "")
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
