"""
Shared template filters and utility functions — DailyAIWire.news
Extracted from app.py during Blueprint refactoring.
"""
import re
from datetime import datetime


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

        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)

        now = datetime.now()
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
        return dt.strftime('%b %d')
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
