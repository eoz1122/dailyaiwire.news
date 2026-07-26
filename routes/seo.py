"""
SEO routes — DailyAIWire.news
Sitemap, robots.txt, RSS feed, and favicon.
"""
import json
from datetime import datetime
from email.utils import formatdate

from flask import Blueprint, render_template, Response, make_response, current_app

from db import get_db_connection
from services.editorials import get_combined_lab_posts
from services.indexing_promotions import fetch_promoted_articles
import logging

logger = logging.getLogger('seo')

seo_bp = Blueprint('seo', __name__)

def _article_sitemap_lastmod(article, fallback):
    try:
        if 'T' in article['published_at']:
            return article['published_at'].split('T')[0]
        return article['published_at'].split(' ')[0]
    except Exception:
        return fallback

@seo_bp.route('/rss.xml')
@seo_bp.route('/feed')
@seo_bp.route('/rss')
def rss_feed():
    conn = get_db_connection()
    articles_db = conn.execute("SELECT * FROM articles WHERE is_published = 1 AND published_at IS NOT NULL AND replace(published_at, 'T', ' ') <= datetime('now') ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()

    articles = []

    # 1. Process Database Articles
    for art in articles_db:
        a = dict(art)
        try:
            ts = a['published_at']
            if 'T' in ts:
                ts = ts.split('.')[0].replace('Z', '')
                dt = datetime.fromisoformat(ts)
            else:
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    dt = datetime.strptime(ts[:10], '%Y-%m-%d')
            dt = dt.replace(tzinfo=None)
            
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
        a['enclosure_length'] = "0"

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
        a['link'] = f"https://dailyaiwire.news/article/{a['slug']}?utm_source=rss&utm_medium=feed&utm_campaign=weekly_rss"
        articles.append(a)

    # 2. Process Lab Posts
    lab_posts = get_combined_lab_posts(published_only=True)
    for post in lab_posts:
        p = dict(post)
        try:
            ts = p['published_at']
            if 'T' in ts:
                ts = ts.split('.')[0].replace('Z', '')
                dt = datetime.fromisoformat(ts)
            else:
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    dt = datetime.strptime(ts[:10], '%Y-%m-%d')
            dt = dt.replace(tzinfo=None)
            
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

        subtitle = p.get('subtitle', '')
        hashtags = " ".join(p.get('hashtags', [])) if isinstance(p.get('hashtags'), list) else ""

        social_copy = []
        if subtitle:
            social_copy.append(subtitle)
        if hashtags:
            social_copy.append(hashtags)

        p['clean_summary'] = "\n\n".join(social_copy) if social_copy else subtitle
        p['link'] = f"https://dailyaiwire.news/lab/{p['slug']}?utm_source=rss&utm_medium=feed&utm_campaign=lab_rss"

        articles.append(p)

    # 3. Sort Combined List by Date DESC
    articles.sort(key=lambda x: x['pub_date_obj'], reverse=True)
    articles = articles[:25]

    xml = render_template('rss.xml', articles=articles, build_date=formatdate())
    response = Response(xml, mimetype='application/rss+xml')
    response.headers["X-Robots-Tag"] = "noindex, follow"
    return response


@seo_bp.route('/rss/linkedin')
def linkedin_rss_feed():
    """Curated, quality-filtered RSS feed for the n8n → LinkedIn pipeline.

    Filters:
    - importance_score >= 75 for stronger social relevance
    - Max 12 articles per category and 8 per source
    - Max 8 research-paper items
    - Hard cap of 50 articles
    """
    conn = get_db_connection()

    # LinkedIn needs a tighter social feed than the public RSS feed. Research
    # papers are valuable onsite, but they should not dominate social posting.
    query = '''
        WITH eligible AS (
            SELECT *,
                CASE
                    WHEN lower(COALESCE(source, '')) IN (
                        'hugging face papers',
                        'arxiv cs.ai',
                        'arxiv research'
                    )
                    OR lower(COALESCE(source_url, '')) LIKE '%huggingface.co/papers%'
                    OR lower(COALESCE(source_url, '')) LIKE '%arxiv.org/%'
                    THEN 1
                    ELSE 0
                END AS is_research_item
            FROM articles
            WHERE is_published = 1
              AND importance_score >= 75
              AND published_at IS NOT NULL
              AND replace(published_at, 'T', ' ') <= datetime('now')
              AND lower(COALESCE(source, '')) NOT IN (
                  'the motley fool',
                  'morningstar',
                  'seeking alpha',
                  'investorplace',
                  'tipranks'
              )
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY category
                    ORDER BY published_at DESC
                ) AS category_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY source
                    ORDER BY published_at DESC
                ) AS source_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY is_research_item
                    ORDER BY published_at DESC
                ) AS research_rank
            FROM eligible
        )
        SELECT *
        FROM ranked
        WHERE category_rank <= 12
          AND source_rank <= 8
          AND (is_research_item = 0 OR research_rank <= 8)
        ORDER BY published_at DESC
        LIMIT 50
    '''
    articles_db = conn.execute(query).fetchall()
    conn.close()

    articles = []
    for art in articles_db:
        a = dict(art)
        try:
            ts = a['published_at']
            if 'T' in ts:
                ts = ts.split('.')[0].replace('Z', '')
                dt = datetime.fromisoformat(ts)
            else:
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    dt = datetime.strptime(ts[:10], '%Y-%m-%d')
            dt = dt.replace(tzinfo=None)

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

        # Social Copy (same format as main RSS)
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
        a['link'] = f"https://dailyaiwire.news/article/{a['slug']}?utm_source=linkedin&utm_medium=social&utm_campaign=linkedin_rss"
        articles.append(a)

    # Inject published editorials (blog_posts) into the LinkedIn feed
    conn = get_db_connection()
    try:
        editorial_rows = conn.execute('''
            SELECT * FROM blog_posts
            WHERE is_published = 1 AND published_at IS NOT NULL
            ORDER BY published_at DESC
            LIMIT 5
        ''').fetchall()
    except Exception:
        editorial_rows = []
    conn.close()

    for row in editorial_rows:
        e = dict(row)
        try:
            ts = e['published_at']
            if 'T' in ts:
                ts = ts.split('.')[0].replace('Z', '')
                dt = datetime.fromisoformat(ts)
            else:
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    dt = datetime.strptime(ts[:10], '%Y-%m-%d')
            dt = dt.replace(tzinfo=None)
            e['pub_date_obj'] = dt
            e['pub_date_rss'] = formatdate(float(dt.timestamp()))
        except Exception:
            e['pub_date_obj'] = datetime.now()
            e['pub_date_rss'] = formatdate()

        img_url = e.get('image') or 'https://dailyaiwire.news/static/fallbacks/editorial_0.jpg'
        if img_url.startswith('/'):
            img_url = f"https://dailyaiwire.news{img_url}"
        e['enclosure_url'] = img_url
        e['enclosure_type'] = 'image/jpeg'

        gist = e.get('gist') or e.get('subtitle') or e.get('meta_description') or ''
        impact = e.get('impact', '')
        social_parts = []
        if gist:
            social_parts.append(gist)
        if impact:
            social_parts.append(f"Impact: {impact}")
        social_parts.append('#DailyAIWire #AI #Opinion')

        e['clean_summary'] = "\n\n".join(social_parts)
        e['link'] = f"https://dailyaiwire.news/lab/{e['slug']}?utm_source=linkedin&utm_medium=social&utm_campaign=linkedin_rss"
        # Ensure required fields exist for rss.xml template compatibility
        e.setdefault('title', e.get('title', 'Editorial'))
        e.setdefault('category', 'Editorial')
        e.setdefault('source', 'DailyAIWire Editorial')
        e['is_research_item'] = 0
        articles.append(e)

    # Re-sort combined list and apply hard cap
    articles.sort(key=lambda x: x.get('pub_date_obj', datetime.min), reverse=True)
    articles = articles[:50]

    xml = render_template(
        'rss.xml',
        articles=articles,
        build_date=formatdate(),
        linkedin_feed=True,
    )
    response = Response(xml, mimetype='application/rss+xml')
    response.headers["X-Robots-Tag"] = "noindex, follow"
    return response


@seo_bp.route('/sitemap.xml', methods=['GET'])
def sitemap_index():
    """Serve the single promoted-content sitemap during indexing recovery."""
    now_str = datetime.now().strftime('%Y-%m-%d')
    sitemaps = [
        {'loc': 'https://dailyaiwire.news/sitemap-core.xml', 'lastmod': now_str},
    ]
    xml = render_template('sitemap_index.xml', sitemaps=sitemaps)
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=3600"
    return response


@seo_bp.route('/sitemap-core.xml', methods=['GET'])
def sitemap_core():
    """Core sitemap: static pages, promoted articles, and human editorials."""
    base_url = "https://dailyaiwire.news"
    pages = []
    now_str = datetime.now().strftime('%Y-%m-%d')

    # Static Pages (always included)
    pages.append([base_url + "/", 1.0, "daily", now_str])
    pages.append([base_url + "/about", 0.5, "monthly", now_str])
    pages.append([base_url + "/contact", 0.5, "monthly", now_str])
    pages.append([base_url + "/privacy", 0.5, "yearly", now_str])
    pages.append([base_url + "/impressum", 0.4, "yearly", now_str])
    pages.append([base_url + "/how-it-works", 0.7, "monthly", now_str])
    pages.append([base_url + "/subscribe", 0.6, "monthly", now_str])
    pages.append([base_url + "/lab", 0.8, "weekly", now_str])
    pages.append([base_url + "/signal", 0.7, "weekly", now_str])
    pages.append([base_url + "/podcast", 0.7, "weekly", now_str])

    # Recovery mode: the fetcher promotes at most one article per UTC day.
    try:
        for article in fetch_promoted_articles():
            pages.append([
                f"{base_url}/article/{article['slug']}",
                0.8,
                "weekly",
                _article_sitemap_lastmod(article, now_str),
            ])
    except Exception as e:
        logger.error("Sitemap Core Error (Promoted Articles): %s", e)

    # Lab Posts (always in core — editorial content)
    try:
        lab_posts = get_combined_lab_posts(published_only=True)
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
        logger.error("Sitemap Core Error (Lab): %s", e)

    sitemap_xml = render_template('sitemap_template.xml', pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=3600"
    return response


@seo_bp.route('/sitemap-archive.xml', methods=['GET'])
def sitemap_archive():
    """Return an empty legacy archive so previously submitted URLs resolve cleanly."""
    pages = []

    sitemap_xml = render_template('sitemap_template.xml', pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    response.headers["Cache-Control"] = "public, max-age=21600, s-maxage=21600"
    return response


@seo_bp.route('/robots.txt')
def robots():
    """Serve robots.txt from static to keep a single source of truth."""
    response = current_app.send_static_file('robots.txt')
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=3600"
    return response


@seo_bp.route('/favicon.ico')
def favicon():
    return current_app.send_static_file('favicon.png')


@seo_bp.route('/apple-touch-icon.png')
@seo_bp.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    """Serve the site icon for common browser/mobile icon discovery paths."""
    return current_app.send_static_file('favicon.png')


@seo_bp.route('/llms.txt')
@seo_bp.route('/.well-known/llms.txt')
def llms_txt():
    """Serve llms.txt for AI crawler guidance (Phase 3: GEO)."""
    return current_app.send_static_file('llms.txt')
