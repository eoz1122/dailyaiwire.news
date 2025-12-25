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

    # Categories
    categories = conn.execute('SELECT category FROM articles WHERE category IS NOT NULL GROUP BY category').fetchall()
    for cat in categories:
        xml.append('<url>')
        xml.append(f'<loc>https://dailyaiwire.news/?category={cat["category"]}</loc>')
        xml.append(f'<lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
        xml.append('<changefreq>daily</changefreq>')
        xml.append('<priority>0.8</priority>')
        xml.append('</url>')
    
    # Articles
    now = datetime.now()
    for article in articles:
        xml.append('<url>')
        xml.append(f'<loc>https://dailyaiwire.news/article/{article["slug"]}</loc>')
        
        # Calculate age for dynamic changefreq
        changefreq = "monthly"
        priority = "0.7"
        
        if article['published_at']:
            try:
                # Handle potential formats (ISO string)
                pub_dt = datetime.fromisoformat(article['published_at'].replace('Z', '+00:00'))
                age_days = (now - pub_dt).days
                
                if age_days < 1:
                    changefreq = "hourly"
                    priority = "0.9"
                elif age_days < 7:
                    changefreq = "daily"
                    priority = "0.8"
                else:
                    changefreq = "weekly"
                    priority = "0.6"
                    
                pub_date = pub_dt.strftime("%Y-%m-%d")
            except:
                pub_date = article['published_at'][:10]
        else:
            pub_date = now.strftime("%Y-%m-%d")
            
        xml.append(f'<lastmod>{pub_date}</lastmod>')
        xml.append(f'<changefreq>{changefreq}</changefreq>')
        xml.append(f'<priority>{priority}</priority>')
        xml.append('</url>')
    
    # Blog posts
    for post in blog_posts:
        xml.append('<url>')
        xml.append(f'<loc>https://dailyaiwire.news/lab/{post["slug"]}</loc>')
        
        changefreq = "weekly"
        if post['published_at']:
            try:
                pub_dt = datetime.fromisoformat(post['published_at'].replace('Z', '+00:00'))
                if (now - pub_dt).days < 30:
                    changefreq = "daily"
                pub_date = pub_dt.strftime("%Y-%m-%d")
            except:
                pub_date = post['published_at'][:10]
        else:
            pub_date = now.strftime("%Y-%m-%d")
            
        xml.append(f'<lastmod>{pub_date}</lastmod>')
        xml.append(f'<changefreq>{changefreq}</changefreq>')
        xml.append('<priority>0.8</priority>')
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
