"""
SEO routes — DailyAIWire.news
Sitemap, robots.txt, RSS feed, and favicon.
"""
import json
from datetime import datetime
from email.utils import formatdate

from flask import Blueprint, render_template, Response, make_response, current_app

from db import get_db_connection
from lab_posts import get_lab_posts, get_lab_post

seo_bp = Blueprint('seo', __name__)


def get_combined_lab_posts():
    """Fetch posts from both lab_posts.py and the blog_posts DB table."""
    posts = list(get_lab_posts())

    conn = get_db_connection()
    try:
        rows = conn.execute('SELECT * FROM blog_posts').fetchall()
        for r in rows:
            posts.append(dict(r))
    except Exception:
        pass  # Table might not exist yet
    conn.close()

    posts.sort(key=lambda x: x.get('published_at', ''), reverse=True)
    return posts


@seo_bp.route('/rss.xml')
@seo_bp.route('/feed')
@seo_bp.route('/rss')
def rss_feed():
    conn = get_db_connection()
    articles_db = conn.execute("SELECT * FROM articles WHERE published_at IS NOT NULL AND replace(published_at, 'T', ' ') <= datetime('now') ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()

    articles = []

    # 1. Process Database Articles
    for art in articles_db:
        a = dict(art)
        try:
            clean_date = a['published_at'].replace('T', ' ').split('.')[0]
            try:
                dt = datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(clean_date[:10], '%Y-%m-%d')

            a['pub_date_obj'] = dt
            a['pub_date_rss'] = formatdate(float(dt.timestamp()))
        except Exception:
            a['pub_date_obj'] = datetime.now()
            a['pub_date_rss'] = formatdate()

        # Enclosure
        img_url = a.get('image') or "https://dailyaiwire.news/static/fallbacks/tools_0.jpg"
        if img_url.startswith('/'):
            img_url = f"https://dailyaiwire.news{img_url}"
        a['enclosure_url'] = img_url
        a['enclosure_type'] = "image/jpeg" if "png" not in img_url.lower() else "image/png"

        # Social Copy
        question = a.get('thought_provoking_question', '')
        gist = a.get('gist', '') or a.get('title', '')

        hashtags_str = ""
        if a.get('hashtags'):
            try:
                hashtags = json.loads(a['hashtags']) if isinstance(a['hashtags'], str) else a['hashtags']
                if hashtags:
                    hashtags_str = " ".join(hashtags)
            except Exception:
                pass

        social_parts = []
        if gist:
            social_parts.append(gist)

        wim = a.get('why_it_matters', '')
        if wim:
            social_parts.append(f"Why it matters: {wim}")

        if question:
            social_parts.append(f"🤔 {question}")

        if hashtags_str:
            social_parts.append(hashtags_str)

        a['clean_summary'] = "\n\n".join(social_parts)
        a['link'] = f"https://dailyaiwire.news/article/{a['slug']}"
        articles.append(a)

    # 2. Process Lab Posts
    lab_posts = get_combined_lab_posts()
    for post in lab_posts:
        p = dict(post)
        try:
            clean_date = p['published_at'].replace('T', ' ').split('.')[0]
            try:
                dt = datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(clean_date[:10], '%Y-%m-%d')

            p['pub_date_obj'] = dt
            p['pub_date_rss'] = formatdate(float(dt.timestamp()))
        except Exception:
            p['pub_date_obj'] = datetime(2025, 1, 1)
            p['pub_date_rss'] = formatdate(float(p['pub_date_obj'].timestamp()))

        img_url = p.get('image') or "/static/img/default_lab.jpg"
        if img_url.startswith('/'):
            img_url = f"https://dailyaiwire.news{img_url}"
        p['enclosure_url'] = img_url
        p['enclosure_type'] = "image/jpeg"
        p['enclosure_length'] = "0"

        question = p.get('thought_provoking_question', '')
        subtitle = p.get('subtitle', '')
        hashtags = " ".join(p.get('hashtags', [])) if isinstance(p.get('hashtags'), list) else ""

        social_copy = []
        if subtitle:
            social_copy.append(subtitle)
        if hashtags:
            social_copy.append(hashtags)

        p['clean_summary'] = "\n\n".join(social_copy) if social_copy else subtitle
        p['link'] = f"https://dailyaiwire.news/lab/{p['slug']}"

        articles.append(p)

    # 3. Sort Combined List by Date DESC
    articles.sort(key=lambda x: x['pub_date_obj'], reverse=True)
    articles = articles[:25]

    xml = render_template('rss.xml', articles=articles, build_date=formatdate())
    return Response(xml, mimetype='application/xml')


@seo_bp.route('/sitemap.xml', methods=['GET'])
def sitemap():
    """Generates a dynamic XML sitemap for Google Indexing."""
    base_url = "https://dailyaiwire.news"
    pages = []
    now_str = datetime.now().strftime('%Y-%m-%d')

    # Static Pages
    pages.append([base_url + "/", 1.0, "daily", now_str])
    pages.append([base_url + "/about", 0.5, "monthly", now_str])
    pages.append([base_url + "/contact", 0.5, "monthly", now_str])
    pages.append([base_url + "/privacy", 0.5, "yearly", now_str])
    pages.append([base_url + "/lab", 0.8, "weekly", now_str])

    conn = get_db_connection()

    # 1. Categories
    try:
        categories = conn.execute('SELECT category FROM articles WHERE category IS NOT NULL GROUP BY category').fetchall()
        for cat in categories:
            url = f"{base_url}/?category={cat['category']}"
            pages.append([url, 0.8, "daily", now_str])
    except Exception as e:
        print(f"Sitemap Error (Categories): {e}")

    # 2. Dynamic Articles
    try:
        query = """
            SELECT slug, published_at FROM articles
            WHERE is_published = 1
            AND replace(published_at, 'T', ' ') <= datetime('now')
            ORDER BY published_at DESC
            LIMIT 50
        """
        articles_rows = conn.execute(query).fetchall()
        for art in articles_rows:
            url = f"{base_url}/article/{art['slug']}"
            try:
                if 'T' in art['published_at']:
                    pub_date = art['published_at'].split('T')[0]
                else:
                    pub_date = art['published_at'].split(' ')[0]
            except Exception:
                pub_date = now_str
            pages.append([url, 0.8, "daily", pub_date])
    except Exception as e:
        print(f"Sitemap Error (Articles): {e}")

    conn.close()

    # 3. Lab Posts
    try:
        lab_posts = get_combined_lab_posts()
        for post in lab_posts:
            url = f"{base_url}/lab/{post['slug']}"
            try:
                if 'T' in post['published_at']:
                    pub_date = post['published_at'].split('T')[0]
                else:
                    pub_date = post['published_at'].split(' ')[0]
            except Exception:
                pub_date = now_str
            pages.append([url, 0.8, "weekly", pub_date])
    except Exception as e:
        print(f"Sitemap Error (Lab): {e}")

    sitemap_xml = render_template('sitemap_template.xml', pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response


@seo_bp.route('/robots.txt')
def robots():
    """Serves the standard robots.txt file."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /login",
        "",
        "Sitemap: https://dailyaiwire.news/sitemap.xml"
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@seo_bp.route('/favicon.ico')
def favicon():
    return current_app.send_static_file('favicon.png')
