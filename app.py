import os
import sqlite3
import json
from datetime import datetime
from flask import Flask, render_template, abort, request, Response

app = Flask(__name__)
DB_PATH = "news.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

    return conn

@app.context_processor
def inject_config():
    return {
        'config_ga_id': os.getenv('GA_MEASUREMENT_ID'),
        'current_year': datetime.now().year
    }

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    q = request.args.get('q', '').strip()
    per_page = 17  # 8 for carousel + 9 for grid
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Get top 12 categories for the filter bar
    categories_raw = conn.execute('''
        SELECT category FROM articles 
        WHERE category IS NOT NULL 
        GROUP BY category 
        ORDER BY COUNT(*) DESC 
        LIMIT 12
    ''').fetchall()
    categories = sorted([c['category'] for c in categories_raw])
    
    if q:
        # Search query
        search_pattern = f"%{q}%"
        articles = conn.execute('''
            SELECT * FROM articles 
            WHERE title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ?
            ORDER BY published_at DESC LIMIT ? OFFSET ?
        ''', (search_pattern, search_pattern, search_pattern, per_page, offset)).fetchall()
        total_articles = conn.execute('''
            SELECT COUNT(*) FROM articles 
            WHERE title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ?
        ''', (search_pattern, search_pattern, search_pattern)).fetchone()[0]
    elif category:
        articles = conn.execute('SELECT * FROM articles WHERE category = ? ORDER BY published_at DESC LIMIT ? OFFSET ?', (category, per_page, offset)).fetchall()
        total_articles = conn.execute('SELECT COUNT(*) FROM articles WHERE category = ?', (category,)).fetchone()[0]
    else:
        articles = conn.execute('SELECT * FROM articles ORDER BY published_at DESC LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
        total_articles = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        
    total_pages = (total_articles + per_page - 1) // per_page
    conn.close()
    
    # Process JSON fields for template
    processed_articles = []
    for art in articles:
        article_dict = dict(art)
        try:
            article_dict['key_details'] = json.loads(art['key_details'])
        except:
            article_dict['key_details'] = []
        processed_articles.append(article_dict)
    
    # Separate carousel articles (first 8) from grid articles (next 9)
    carousel_articles = processed_articles[:8] if len(processed_articles) >= 8 else []
    grid_articles = processed_articles[8:17] if len(processed_articles) > 8 else processed_articles
        
    return render_template('index.html', 
                          articles=grid_articles,
                          carousel_articles=carousel_articles,
                          page=page, 
                          total_pages=total_pages,
                          category=category,
                          categories=categories,
                          q=q)

@app.route('/article/<slug>')
def article(slug):
    conn = get_db_connection()
    article = conn.execute('SELECT * FROM articles WHERE slug = ?', (slug,)).fetchone()
    conn.close()
    
    if article is None:
        abort(404)
        
    article_dict = dict(article)
    try:
        article_dict['key_details'] = json.loads(article['key_details'])
    except:
        article_dict['key_details'] = []
    return render_template('article.html', article=article_dict)

@app.route('/lab')
def lab_index():
    conn = get_db_connection()
    posts = conn.execute('SELECT * FROM blog_posts ORDER BY published_at DESC').fetchall()
    conn.close()
    return render_template('lab_index.html', posts=posts)

@app.route('/lab/<slug>')
def lab_post(slug):
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM blog_posts WHERE slug = ?', (slug,)).fetchone()
    conn.close()
    if post is None:
        abort(404)
    return render_template('lab_post.html', post=post)

@app.route('/rss')
def rss():
    conn = get_db_connection()
    articles = conn.execute('SELECT * FROM articles ORDER BY published_at DESC LIMIT 50').fetchall()
    conn.close()
    
    processed_articles = []
    for art in articles:
        article_dict = dict(art)
        # Format date for RSS (RFC 822)
        try:
            dt = datetime.fromisoformat(art['published_at'])
            article_dict['pub_date_rss'] = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
        except:
            article_dict['pub_date_rss'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        processed_articles.append(article_dict)
    
    # Template rendering for XML
    rss_xml = render_template('rss.xml', 
                             articles=processed_articles, 
                             build_date=datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT'))
    return Response(rss_xml, mimetype='application/xml')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# Import SEO routes (sitemap, robots.txt)
import seo_routes

if __name__ == '__main__':
    # Development server
    app.run(debug=True, port=5000)
