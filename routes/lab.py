"""
Lab routes — DailyAIWire.news
Lab/editorial blog index and single post pages.
"""
from flask import Blueprint, render_template, abort

from db import get_db_connection
from lab_posts import get_lab_post as get_lab_post_from_file
from services.editorials import (
    EDITORIAL_FALLBACK_IMAGE,
    get_combined_lab_posts,
)

lab_bp = Blueprint('lab', __name__)

@lab_bp.route('/lab')
def lab_index():
    posts = get_combined_lab_posts(published_only=True)
    return render_template('lab_index.html', posts=posts)


@lab_bp.route('/lab/<slug>')
def lab_post(slug):
    post = get_lab_post_from_file(slug)

    # If not in file, check DB
    if not post:
        conn = get_db_connection()
        try:
            row = conn.execute('SELECT * FROM blog_posts WHERE slug = ?', (slug,)).fetchone()
            if row:
                post = dict(row)
                if not post.get('image'):
                    post['image'] = EDITORIAL_FALLBACK_IMAGE
        except Exception:
            pass
        conn.close()

    if not post:
        abort(404)

    return render_template('lab_post.html', post=post)
