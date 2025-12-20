import os
import sqlite3
import json
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, abort, request, Response, make_response
from dotenv import load_dotenv

load_dotenv()

# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

app = Flask(__name__)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('DailyAIWire startup')
DB_PATH = "news.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.context_processor
def inject_config():
    def category_color(cat):
        cat = (cat or "").lower()
        if any(w in cat for w in ['sec', 'cyb', 'hack']): return 'bg-red-600'
        if any(w in cat for w in ['robot', 'hard', 'auto']): return 'bg-orange-600'
        if any(w in cat for w in ['llm', 'gen', 'gpt', 'model', 'res']): return 'bg-purple-600'
        if any(w in cat for w in ['fin', 'mark', 'invest', 'biz', 'ent']): return 'bg-blue-700'
        if any(w in cat for w in ['med', 'bio', 'health']): return 'bg-teal-600'
        return 'bg-indigo-600'

    # Global Author Metadata - 100% Resistant to Database issues
    emre_profile = {
        'name': 'Emre Ozen',
        'title': 'VP, Head of Ad Operations & Analytics',
        'bio': 'With 12 years in the programmatic space, I’ve managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I’m now focused on integrating AI and automation to streamline the heavy lifting of digital advertising. I’m a self-motivated builder who loves using smart tech to make marketing more strategic and efficient.',
        'linkedin': 'https://www.linkedin.com/in/emreozen/',
        'image': 'https://media.licdn.com/dms/image/v2/C4D03AQEa1z_lV0c9vQ/profile-displayphoto-shrink_800_800/profile-displayphoto-shrink_800_800/0/1516260952865?e=1740009600&v=beta&t=H-W6z6x9x-x-x-x-x-x-x-x'
    }

    return {
        'config_ga_id': os.getenv('GA_MEASUREMENT_ID'),
        'current_year': datetime.now().year,
        'category_color': category_color,
        'emre': emre_profile
    }

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    q = request.args.get('q', '').strip()
    # Dynamic per_page and offset to handle Carousel vs Grid layout
    if page == 1:
        per_page = 14 # 8 for carousel + 6 for grid
        offset = 0
    else:
        per_page = 12 # Standard grid size for deeper pages
        offset = 14 + (page - 2) * per_page

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
            ORDER BY id DESC LIMIT ? OFFSET ?
        ''', (search_pattern, search_pattern, search_pattern, per_page, offset)).fetchall()
        total_articles = conn.execute('''
            SELECT COUNT(*) FROM articles 
            WHERE title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ?
        ''', (search_pattern, search_pattern, search_pattern)).fetchone()[0]
    elif category:
        articles = conn.execute('SELECT * FROM articles WHERE category = ? ORDER BY id DESC LIMIT ? OFFSET ?', (category, per_page, offset)).fetchall()
        total_articles = conn.execute('SELECT COUNT(*) FROM articles WHERE category = ?', (category,)).fetchone()[0]
    else:
        articles = conn.execute('SELECT * FROM articles ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
        total_articles = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        
    # Calculate total pages (adjusting for irregular page 1)
    if total_articles <= 14:
        total_pages = 1
    else:
        total_pages = 1 + ((total_articles - 14 + per_page - 1) // per_page)
        
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
    
    # Selection logic for Carousel (unique to page 1)
    if page == 1:
        carousel_articles = processed_articles[:8]
        grid_articles = processed_articles[8:14] # Exactly 6 unique tiles
    else:
        carousel_articles = []
        grid_articles = processed_articles # Full grid on deeper pages
        
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

@app.route('/about')
def about():
    # We can pull from the context processor 'emre' data
    return render_template('about.html')

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

# SEO Routes (Integrated from seo_routes.py)
@app.route('/sitemap.xml')
def sitemap():
    conn = get_db_connection()
    articles = conn.execute('SELECT slug, published_at FROM articles ORDER BY published_at DESC').fetchall()
    blog_posts = conn.execute('SELECT slug, published_at FROM blog_posts ORDER BY published_at DESC').fetchall()
    conn.close()
    
    xml = ['<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml.append(f'<url><loc>https://dailyaiwire.news/</loc><priority>1.0</priority></url>')
    xml.append(f'<url><loc>https://dailyaiwire.news/lab</loc><priority>0.8</priority></url>')
    xml.append(f'<url><loc>https://dailyaiwire.news/about</loc><priority>0.8</priority></url>')
    
    for article in articles:
        xml.append(f'<url><loc>https://dailyaiwire.news/article/{article["slug"]}</loc><priority>0.7</priority></url>')
    for post in blog_posts:
        xml.append(f'<url><loc>https://dailyaiwire.news/lab/{post["slug"]}</loc><priority>0.8</priority></url>')
    
    xml.append('</urlset>')
    response = make_response('\n'.join(xml))
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/robots.txt')
def robots():
    try:
        with open('static/robots.txt', 'r') as f:
            content = f.read()
    except:
        content = "User-agent: *\nAllow: /\nSitemap: https://dailyaiwire.news/sitemap.xml"
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain'
    return response

if __name__ == '__main__':
    # Development server
    app.run(debug=True, port=5000)
