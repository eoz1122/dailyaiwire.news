"""
Podcast — DailyAIWire.news
Public podcast page with Spotify episode embeds.
"""
from flask import Blueprint, render_template

podcast_bp = Blueprint('podcast', __name__)


@podcast_bp.route('/podcast')
def podcast_page():
    """Public podcast page with embedded Spotify episodes."""
    return render_template('podcast.html')
