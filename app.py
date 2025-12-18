import os
import sqlite3
import json
from flask import Flask, render_template, abort, request

app = Flask(__name__)
DB_PATH = "news.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    per_page = 12
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Get all unique categories for the filter bar
    categories_raw = conn.execute('SELECT DISTINCT category FROM articles WHERE category IS NOT NULL').fetchall()
    categories = [c['category'] for c in categories_raw]
    
    if category:
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
        
    return render_template('index.html', 
                          articles=processed_articles, 
                          page=page, 
                          total_pages=total_pages,
                          category=category,
                          categories=categories)

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
