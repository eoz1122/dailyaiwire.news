from flask import make_response, request
from app import app, get_db_connection
from datetime import datetime

@app.route('/sitemap.xml')
def sitemap():
    """Generate XML sitemap for search engines"""
    conn = get_db_connection()
    
    # Get all articles
    articles = conn.execute('''
        SELECT slug, published_at 
        FROM articles 
        ORDER BY published_at DESC
    ''').fetchall()
    
    # Get all blog posts
    blog_posts = conn.execute('''
        SELECT slug, published_at 
        FROM blog_posts 
        ORDER BY published_at DESC
    ''').fetchall()
    
    conn.close()
    
    # Build sitemap XML
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # Homepage
    xml.append('<url>')
    xml.append('<loc>https://dailyaiwire.news/</loc>')
    xml.append(f'<lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('<changefreq>hourly</changefreq>')
    xml.append('<priority>1.0</priority>')
    xml.append('</url>')
    
    # Lab index
    xml.append('<url>')
    xml.append('<loc>https://dailyaiwire.news/lab</loc>')
    xml.append(f'<lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('<changefreq>weekly</changefreq>')
    xml.append('<priority>0.8</priority>')
    xml.append('</url>')
    
    # Articles
    for article in articles:
        xml.append('<url>')
        xml.append(f'<loc>https://dailyaiwire.news/article/{article["slug"]}</loc>')
        if article['published_at']:
            pub_date = article['published_at'][:10] if isinstance(article['published_at'], str) else datetime.now().strftime("%Y-%m-%d")
            xml.append(f'<lastmod>{pub_date}</lastmod>')
        xml.append('<changefreq>monthly</changefreq>')
        xml.append('<priority>0.7</priority>')
        xml.append('</url>')
    
    # Blog posts
    for post in blog_posts:
        xml.append('<url>')
        xml.append(f'<loc>https://dailyaiwire.news/lab/{post["slug"]}</loc>')
        if post['published_at']:
            pub_date = post['published_at'][:10] if isinstance(post['published_at'], str) else datetime.now().strftime("%Y-%m-%d")
            xml.append(f'<lastmod>{pub_date}</lastmod>')
        xml.append('<changefreq>monthly</changefreq>')
        xml.append('<priority>0.6</priority>')
        xml.append('</url>')
    
    xml.append('</urlset>')
    
    response = make_response('\n'.join(xml))
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/robots.txt')
def robots():
    """Serve robots.txt"""
    with open('static/robots.txt', 'r') as f:
        content = f.read()
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain'
    return response
