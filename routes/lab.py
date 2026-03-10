"""
Lab routes — DailyAIWire.news
Lab/editorial blog index and single post pages.
"""
from flask import Blueprint, render_template, abort

from db import get_db_connection
from lab_posts import get_lab_posts, get_lab_post as get_lab_post_from_file

lab_bp = Blueprint('lab', __name__)


def get_combined_lab_posts():
    """Fetch posts from both lab_posts.py and the blog_posts DB table."""
    posts = list(get_lab_posts())

    conn = get_db_connection()
    try:
        rows = conn.execute('SELECT * FROM blog_posts').fetchall()
        for r in rows:
            posts.append(dict(r))
    except Exception:
        pass
    conn.close()

    posts.sort(key=lambda x: x.get('published_at', ''), reverse=True)
    return posts


@lab_bp.route('/lab')
def lab_index():
    posts = get_combined_lab_posts()
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
        except Exception:
            pass
        conn.close()

    if not post:
        abort(404)

    return render_template('lab_post.html', post=post)
