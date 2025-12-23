import os, sqlite3, json, math, re
from datetime import datetime
from flask import Flask, render_template, abort, request, Response
from email.utils import formatdate
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

def remove_emojis(text):
    if not text: return ""
    return re.sub(r'[\U00010000-\U0010ffff]', '', text)

app.jinja_env.filters['remove_emojis'] = remove_emojis

def time_ago(dt_str):
    if not dt_str: return ""
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            try:
                dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            except:
                dt = datetime.strptime(dt_str, '%Y-%m-%d')
        
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
            
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        
        if seconds < 0: return "just now"
        if seconds < 60: return f"{seconds}s ago"
        if seconds < 3600: return f"{seconds // 60}m ago"
        if seconds < 86400: return f"{seconds // 3600}h ago"
        if seconds < 604800: return f"{seconds // 86400}d ago"
        return dt.strftime('%b %d')
    except:
        return dt_str

app.jinja_env.filters['time_ago'] = time_ago
DB_PATH = os.path.join(os.path.dirname(__file__), "news.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.context_processor
def inject_config():
    local_img = os.path.join(app.static_folder, 'emre.jpg')
    img = '/static/emre.jpg' if os.path.exists(local_img) else "https://ui-avatars.com/api/?name=Emre+Ozen&size=512&background=2563eb&color=fff"
    
    def get_cat_color(c):
        colors = {
            'Business': 'bg-indigo-600',
            'Technology': 'bg-emerald-600',
            'Policy': 'bg-red-600',
            'Science': 'bg-teal-600',
            'Tools': 'bg-amber-600',
            'Security': 'bg-violet-600',
            'Finance': 'bg-green-600',
            'Health': 'bg-rose-600',
            'Energy': 'bg-yellow-600',
            'LLMs': 'bg-purple-600',
            'Robotics': 'bg-cyan-600',
            'Society': 'bg-pink-600'
        }
        return colors.get(c, 'bg-blue-600')

    return {
        'current_year': datetime.now().year,
        'config_ga_id': os.getenv('GA_MEASUREMENT_ID'),
        'q': request.args.get('q', ''),
        'emre': {
            'name': 'Emre Ozen',
            'title': 'VP, Head of Ad Operations & Analytics',
            'bio': 'With 12 years in the programmatic space, I’ve managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I\'m now focused on integrating AI and automation to streamline the heavy lifting of digital advertising.',
            'linkedin': 'https://www.linkedin.com/in/emreozen/',
            'image': img
        },
        'category_color': get_cat_color
    }

@app.route('/')
def index():
    conn = get_db_connection()
    cats = conn.execute('SELECT category FROM articles WHERE category IS NOT NULL GROUP BY category LIMIT 12').fetchall()
    categories = sorted([c['category'] for c in cats])
    
    page = request.args.get('page', 1, type=int)
    cat_arg = request.args.get('category')
    q = request.args.get('q', '')
    
    ITEMS_PER_PAGE = 9

    if q:
        query = f"%{q}%"
        offset = (page - 1) * ITEMS_PER_PAGE
        total_arts = conn.execute('SELECT COUNT(*) FROM articles WHERE title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ?', (query, query, query)).fetchone()[0]
        grid = conn.execute('SELECT * FROM articles WHERE title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ? ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', (query, query, query, ITEMS_PER_PAGE, offset)).fetchall()
        carousel = []
    elif cat_arg:
        offset = (page - 1) * ITEMS_PER_PAGE
        total_arts_count = conn.execute('SELECT COUNT(*) FROM articles WHERE category = ?', (cat_arg,)).fetchone()[0]
        total_arts = total_arts_count
        grid = conn.execute('SELECT * FROM articles WHERE category = ? ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', (cat_arg, ITEMS_PER_PAGE, offset)).fetchall()
        carousel = []
    else:
        if page == 1:
            carousel = conn.execute('SELECT * FROM articles ORDER BY published_at DESC, id DESC LIMIT 5').fetchall()
            grid = conn.execute('SELECT * FROM articles ORDER BY published_at DESC, id DESC LIMIT ? OFFSET 5', (ITEMS_PER_PAGE,)).fetchall()
            total_arts_count = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            total_arts = max(0, total_arts_count - 5)
        else:
            db_offset = 5 + ((page - 1) * ITEMS_PER_PAGE)
            grid = conn.execute('SELECT * FROM articles ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', (ITEMS_PER_PAGE, db_offset)).fetchall()
            carousel = []
            total_arts_count = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            total_arts = max(0, total_arts_count - 5)

    conn.close()
    
    total_pages = math.ceil(total_arts / ITEMS_PER_PAGE) if total_arts > 0 else 1

    processed_grid = []
    for a in grid:
        d = dict(a)
        try: d['key_details'] = json.loads(d['key_details'])
        except: d['key_details'] = []
        processed_grid.append(d)

    processed_carousel = []
    for a in carousel:
        d = dict(a)
        try: d['key_details'] = json.loads(d['key_details'])
        except: d['key_details'] = []
        processed_carousel.append(d)

    return render_template('index.html', articles=processed_grid, carousel_articles=processed_carousel, page=page, total_pages=total_pages, categories=categories, category=cat_arg, q=q)

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

@app.route('/article/<slug>')
def article(slug):
    conn = get_db_connection()
    art = conn.execute('SELECT * FROM articles WHERE slug = ?', (slug,)).fetchone()
    conn.close()
    if not art: abort(404)
    d = dict(art)
    try: d['key_details'] = json.loads(art['key_details'])
    except: d['key_details'] = []
    return render_template('article.html', article=d)

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/privacy')
def privacy(): return render_template('privacy.html')

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
    if not post: abort(404)
    return render_template('lab_post.html', post=post)

@app.after_request
def add_header(r):
    r.headers['Cache-Control'] = 'no-store'
    return r

if __name__ == '__main__':
    app.run(debug=False, port=8000)

@app.route('/rss.xml')
@app.route('/feed')
@app.route('/rss')
def rss_feed():
    conn = get_db_connection()
    articles_db = conn.execute('SELECT * FROM articles WHERE published_at IS NOT NULL ORDER BY published_at DESC LIMIT 20').fetchall()
    conn.close()
    
    articles = []
    for art in articles_db:
        a = dict(art)
        try:
            # Assuming YYYY-MM-DD format in DB
            dt = datetime.strptime(a['published_at'], '%Y-%m-%d')
            a['pub_date_rss'] = formatdate(float(dt.timestamp()))
        except:
            a['pub_date_rss'] = formatdate()
        articles.append(a)
        
    xml = render_template('rss.xml', articles=articles, build_date=formatdate())
    return Response(xml, mimetype='application/xml')

import seo_routes
