import os, sqlite3, json, math
from datetime import datetime
from flask import Flask, render_template, abort, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
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
    
    ITEMS_PER_PAGE = 9

    if cat_arg:
        offset = (page - 1) * ITEMS_PER_PAGE
        total_arts_count = conn.execute('SELECT COUNT(*) FROM articles WHERE category = ?', (cat_arg,)).fetchone()[0]
        total_arts = total_arts_count
        arts = conn.execute('SELECT * FROM articles WHERE category = ? ORDER BY id DESC LIMIT ? OFFSET ?', (cat_arg, ITEMS_PER_PAGE, offset)).fetchall()
        carousel = []
        grid = arts
    else:
        if page == 1:
            carousel = conn.execute('SELECT * FROM articles ORDER BY id DESC LIMIT 5').fetchall()
            grid = conn.execute('SELECT * FROM articles ORDER BY id DESC LIMIT ? OFFSET 5', (ITEMS_PER_PAGE,)).fetchall()
            total_arts_count = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            total_arts = max(0, total_arts_count - 5)
        else:
            db_offset = 5 + ((page - 1) * ITEMS_PER_PAGE)
            grid = conn.execute('SELECT * FROM articles ORDER BY id DESC LIMIT ? OFFSET ?', (ITEMS_PER_PAGE, db_offset)).fetchall()
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

    return render_template('index.html', articles=processed_grid, carousel_articles=processed_carousel, page=page, total_pages=total_pages, categories=categories, category=cat_arg)

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
