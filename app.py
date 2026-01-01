import os, sqlite3, json, math, re, shutil, time
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, abort, request, Response, redirect, url_for, flash
from email.utils import formatdate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.model import BaseModelView
from wtforms import TextAreaField
from dotenv import load_dotenv
from lab_posts import get_lab_posts, get_lab_post
from budget_tracker import BudgetTracker

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-dev-secret-key-change-in-prod')

# --- Authentication Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id == os.getenv('ADMIN_USERNAME', 'admin'):
        return User(user_id)
    return None

# --- Admin Views ---
class SecureModelView(BaseModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=request.url))

class ArticleModelView(SecureModelView):
    # Since we are using raw SQLite and not SQLAlchemy ORM with Flask-Admin's usual ModelView, 
    # we need a completely custom ModelView if we were using the base class, 
    # BUT Flask-Admin is heavily tied to ORMs (SQLAlchemy/Mongo).
    # 
    # CRITICAL: Flask-Admin with raw SQLite is extremely complex/unsupported.
    # We must use a simple CRUD implementation or switch project to SQLAlchemy.
    #
    # GIVEN THE CONSTRAINTS and existing code:
    # We will implement a custom AdminIndexView that lists articles and simple custom routes for edit/delete
    # instead of fighting Flask-Admin's ORM requirement on a raw DB project.
    pass

# Re-evaluating: To save time and keep it robust, let's just make custom routes for /admin/dashboard
# protected by Flask-Login, rather than forcing Flask-Admin's ORM views onto raw SQL.
# OR better: Use Flask-Admin's ability to create custom views.

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('login', next=request.url))
        
        # Pagination & Filtering
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page
        
        date_filter = request.args.get('date', type=str) # YYYY-MM-DD
        search_query = request.args.get('q', '', type=str)
        
        conn = get_db_connection()
        
        # Base query structure for WHERE clause
        conditions = []
        params = []
        
        if date_filter:
            conditions.append('date(published_at) = ?')
            params.append(date_filter)
            
        if search_query:
            conditions.append('(title LIKE ? OR original_author LIKE ?)')
            params.append(f'%{search_query}%')
            params.append(f'%{search_query}%')
            
        where_clause = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        
        # Main Articles Query
        query = f'SELECT id, title, category, published_at, slug, importance_score FROM articles{where_clause} ORDER BY published_at DESC LIMIT ? OFFSET ?'
        query_params = params + [per_page, offset]
        
        articles = conn.execute(query, query_params).fetchall()
        
        # Total count for pagination
        total_query = f'SELECT COUNT(*) FROM articles{where_clause}'
        total_query_result = conn.execute(total_query, params).fetchone()
        total = total_query_result[0] if total_query_result else 0
        has_next = (offset + per_page) < total
        
        conn.close()
        
        return self.render('admin/index.html', articles=articles, page=page, has_next=has_next, date_filter=date_filter, q=search_query)



admin = Admin(app, name='DailyAIWire Admin', index_view=MyAdminIndexView())

# --- Newsletter Admin Routes ---

@app.route('/admin/subscribers')
@login_required
def admin_subscribers():
    conn = get_db_connection()
    subscribers = conn.execute('SELECT * FROM subscribers ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/subscribers.html', subscribers=subscribers)

@app.route('/admin/budget')
@login_required
def admin_budget():
    tracker = BudgetTracker()
    usage = tracker.data
    
    total_spent = usage.get('total_spent', 0.0)
    monthly_cap = tracker.monthly_cap
    percent_used = (total_spent / monthly_cap * 100) if monthly_cap > 0 else 0
    
    budget_view = {
        'current_month': usage.get('current_month'),
        'total_spent': total_spent,
        'percent_used': percent_used,
        'monthly_cap': monthly_cap,
        'remaining': max(0, monthly_cap - total_spent),
        'breakdown': usage.get('breakdown', {}),
        'requests': usage.get('requests', 0),
        'tokens_used': usage.get('tokens_used', 0)
    }
    
    return render_template('admin/budget.html', budget=budget_view)

@app.route('/admin/sources')
@login_required
def admin_sources():
    conn = get_db_connection()
    
    # 1. Get Top Sources by Volume
    usage_query = """
        SELECT source, count(*) as count 
        FROM articles 
        WHERE source IS NOT NULL AND source != '' 
        GROUP BY source 
        ORDER BY count DESC 
        LIMIT 50
    """
    sources_raw = conn.execute(usage_query).fetchall()
    
    # 2. Get Blocked Sources
    try:
        blocked_raw = conn.execute('SELECT * FROM blocked_sources ORDER BY added_at DESC').fetchall()
    except sqlite3.OperationalError:
        # Create table if not exists (Lazy Migration for safety)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blocked_sources (
                domain TEXT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        blocked_raw = []

    conn.close()
    
    return render_template('admin/sources.html', sources=sources_raw, blocked=blocked_raw)

@app.route('/admin/block-source', methods=['POST'])
@login_required
def admin_block_source():
    domain = request.form.get('domain')
    if domain:
        conn = get_db_connection()
        try:
            conn.execute('INSERT OR IGNORE INTO blocked_sources (domain) VALUES (?)', (domain,))
            conn.commit()
            flash(f"Blocked source: {domain}")
        except Exception as e:
            flash(f"Error blocking source: {e}")
        conn.close()
    return redirect(url_for('admin_sources'))

@app.route('/admin/unblock-source', methods=['POST'])
@login_required
def admin_unblock_source():
    domain = request.form.get('domain')
    if domain:
        conn = get_db_connection()
        conn.execute('DELETE FROM blocked_sources WHERE domain = ?', (domain,))
        conn.commit()
        conn.close()
        flash(f"Unblocked source: {domain}")
    return redirect(url_for('admin_sources'))

@app.route('/admin/social-queue')
@login_required
def admin_social_queue():
    conn = get_db_connection()
    # Hybrid Sort: Match the Scheduler's logic (Importance + Freshness Bonus)
    articles = conn.execute('''
        SELECT *, 
        (importance_score + 
            CASE 
                WHEN published_at > datetime('now', '-6 hours') THEN 20 
                WHEN published_at > datetime('now', '-12 hours') THEN 10 
                ELSE 0 
            END
        ) as hybrid_rank 
        FROM articles 
        WHERE (shared_on_x = 0 OR shared_on_x IS NULL) 
        ORDER BY hybrid_rank DESC 
        LIMIT 50
    ''').fetchall()
    conn.close()
    
    # Pre-process JSON fields for template
    processed = []
    for a in articles:
        d = dict(a)
        if d.get('hashtags'):
            try:
                d['hashtags'] = json.loads(d['hashtags'])
            except:
                d['hashtags'] = []
        else:
            d['hashtags'] = []
        processed.append(d)
        
    return render_template('admin/social_queue.html', articles=processed)

@app.route('/admin/mark-shared/<int:id>', methods=['POST'])
@login_required
def admin_mark_shared(id):
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE id = ?', 
                 (datetime.utcnow().isoformat(), id))
    conn.commit()
    conn.close()
    flash("Article marked as shared. Automation will skip it.")
    return redirect(url_for('admin_social_queue'))

@app.route('/admin/newsletters')
@login_required
def admin_newsletters():
    conn = get_db_connection()
    newsletters = conn.execute('SELECT * FROM newsletters ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/newsletters.html', newsletters=newsletters)

# --- Editorials / Lab Admin Routes ---

@app.route('/admin/editorials')
@login_required
def admin_editorials():
    conn = get_db_connection()
    # Check if table exists just in case
    try:
        posts = conn.execute('SELECT * FROM blog_posts ORDER BY published_at DESC').fetchall()
    except:
        posts = []
    conn.close()
    return render_template('admin/editorials.html', posts=posts)

@app.route('/admin/editorial/edit/<id>', methods=['GET', 'POST'])
@login_required
def admin_edit_editorial(id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        if not slug:
            slug = slugify(title)
        
        content = request.form.get('content')
        subtitle = request.form.get('subtitle')
        
        # Ensure table exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blog_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE,
                title TEXT,
                subtitle TEXT,
                content TEXT,
                image TEXT,
                author_name TEXT,
                author_title TEXT,
                author_image TEXT,
                author_linkedin TEXT,
                meta_description TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        if id == 'new':
            conn.execute('INSERT INTO blog_posts (title, slug, content, subtitle, published_at) VALUES (?, ?, ?, ?, ?)',
                         (title, slug, content, subtitle, datetime.now()))
        else:
            conn.execute('UPDATE blog_posts SET title=?, slug=?, content=?, subtitle=? WHERE id=?',
                         (title, slug, content, subtitle, id))
        conn.commit()
        conn.close()
        flash('Post saved successfully.')
        return redirect(url_for('admin_editorials'))

    post = {}
    if id != 'new':
        try:
            post_row = conn.execute('SELECT * FROM blog_posts WHERE id = ?', (id,)).fetchone()
            if post_row:
                post = dict(post_row)
        except:
            pass
    
    conn.close()
    return render_template('admin/edit_editorial.html', post=post, id=id)

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


@app.route('/admin/newsletter/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_edit_newsletter(id):
    conn = get_db_connection()
    if request.method == 'POST':
        subject = request.form.get('subject')
        intro_text = request.form.get('intro_text')
        status = request.form.get('status')
        
        conn.execute('UPDATE newsletters SET subject=?, intro_text=?, status=? WHERE id=?', 
                     (subject, intro_text, status, id))
        conn.commit()
        flash("Newsletter updated.")
        return redirect(url_for('admin_newsletters'))

    newsletter = conn.execute('SELECT * FROM newsletters WHERE id=?', (id,)).fetchone()
    if not newsletter:
        abort(404)
    
    # Get associated articles
    article_ids = json.loads(newsletter['article_ids'])
    articles = []
    if article_ids:
        placeholders = ', '.join(['?'] * len(article_ids))
        articles = conn.execute(f'SELECT title, gist FROM articles WHERE id IN ({placeholders})', article_ids).fetchall()
        
    conn.close()
    return render_template('admin/edit_newsletter.html', newsletter=newsletter, articles=articles)

@app.route('/admin/newsletter/delete/<int:id>')
@login_required
def admin_delete_newsletter(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM newsletters WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash("Newsletter deleted.")
    return redirect(url_for('admin_newsletters'))

@app.route('/admin/newsletter/generate')
@login_required
def admin_generate_newsletter():
    import subprocess
    import sys
    # Runs the curator script as a separate process
    try:
        subprocess.Popen([sys.executable, 'weekly_curator.py'], cwd=os.getcwd())
        flash("AI Curation Engine started. Draft will appear in a few seconds.")
    except Exception as e:
        flash(f"Failed to start curation: {e}")
    
    return redirect(url_for('admin_newsletters'))

@app.route('/admin/newsletter/send/<int:id>')
@login_required
def admin_send_newsletter(id):
    from newsletter_sender import send_newsletter
    success = send_newsletter(id)
    if success:
        flash("Signal broadcast successful. Intelligence delivered to subscribers.")
    else:
        flash("Signal broadcast failed. Check logs/API key.")
    
    return redirect(url_for('admin_newsletters'))

@app.route('/admin/newsletter/preview')
@login_required
def admin_newsletter_preview():
    """Renders the newsletter template with mock data for design review."""
    mock_articles = [
        {
            "category": "Artificial Intelligence",
            "title": "Gemini 2.5: The Dawn of True Reasoning Agents",
            "gist": "Google's latest sweep of the Gemini architecture introduces self-correcting logic loops, allowing the model to 'think' twice before responding, effectively eliminating most hallucinations in complex coding tasks.",
            "slug": "gemini-2.5-reasoning-agents"
        },
        {
            "category": "Robotics",
            "title": "Figure 02 Integrates OpenAI Vision for Factory Precision",
            "gist": "The second generation Figure robot now utilizes a specialized vision-language model from OpenAI to identify and sort microscopic manufacturing defects with 99.8% accuracy.",
            "slug": "figure-02-openai-vision"
        },
        {
            "category": "Open Source",
            "title": "Llama 4 Release Signals the End of Proprietary Moats",
            "gist": "Meta's upcoming 400B parameter model is rumored to outperform GPT-5 across all reasoning benchmarks, forcing a massive pivot in the business models of closed-source giants.",
            "slug": "llama-4- proprietary-moats"
        }
    ]
    
    return render_template('email/briefing.html', 
                           subject="[PREVIEW] The Intelligence Briefing: Llama 4 and the Future of Moats",
                           intro_text="This week was a transition from AI as a tool to AI as a teammate. The release of Gemini 2.5 and the rumors surrounding Llama 4 suggest that the scaling laws are still very much in effect, but the 'intelligence' is now moving into the reasoning layer. We are seeing models that don't just predict the next token, but predict the next *intended* outcome.",
                           articles=mock_articles)

@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_edit_article(id):
    conn = get_db_connection()
    if request.method == 'POST':
        # Text Fields
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        published_at = request.form.get('published_at')
        source = request.form.get('source')
        source_url = request.form.get('source_url')
        
        gist = request.form.get('gist')
        why_it_matters = request.form.get('why_it_matters')
        bull_case = request.form.get('bull_case')
        bear_case = request.form.get('bear_case')
        deep_analysis = request.form.get('deep_analysis')
        
        image_url = request.form.get('image_url')

        # File Handling Helper
        def handle_file_upload(file_input_name, folder, article_slug):
            file = request.files.get(file_input_name)
            if file and file.filename:
                # Ensure directory
                save_dir = os.path.join(app.static_folder, folder)
                os.makedirs(save_dir, exist_ok=True)
                
                # Secure name + simple timestamp to avoid cache
                filename = secure_filename(file.filename)
                # optionally prefix with slug
                name, ext = os.path.splitext(filename)
                new_filename = f"{article_slug}_{name[:20]}_{int(time.time())}{ext}"
                
                path = os.path.join(save_dir, new_filename)
                file.save(path)
                return f"/static/{folder}/{new_filename}"
            return None

        # --- Current DB State ---
        current = conn.execute('SELECT image, audio_male, audio_female FROM articles WHERE id=?', (id,)).fetchone()
        
        # --- Handle Deletes (Checkboxes) ---
        new_image = current['image']
        new_audio_male = current['audio_male']
        new_audio_female = current['audio_female']

        if request.form.get('delete_image'): new_image = None
        if request.form.get('delete_audio_male'): new_audio_male = None
        if request.form.get('delete_audio_female'): new_audio_female = None

        # --- Handle Uploads ---
        # Image
        import time 
        uploaded_image = handle_file_upload('image_file', 'uploads', slug or 'art')
        if uploaded_image:
            new_image = uploaded_image
        elif image_url: # If URL provided text input
            new_image = image_url
            
        # Audio
        uploaded_male = handle_file_upload('audio_male_file', 'audio', slug or 'art')
        if uploaded_male: new_audio_male = uploaded_male
        
        uploaded_female = handle_file_upload('audio_female_file', 'audio', slug or 'art')
        if uploaded_female: new_audio_female = uploaded_female

        conn.execute('''
            UPDATE articles 
            SET title = ?, slug = ?, category = ?, published_at = ?, source = ?, source_url = ?,
                gist = ?, why_it_matters = ?, bull_case = ?, bear_case = ?, deep_analysis = ?,
                image = ?, audio_male = ?, audio_female = ?
            WHERE id = ?
        ''', (title, slug, category, published_at, source, source_url, gist, why_it_matters, bull_case, bear_case, deep_analysis, 
              new_image, new_audio_male, new_audio_female, id))
        conn.commit()
        conn.close()
        flash('Article updated successfully!')
        return redirect(url_for('admin_edit_article', id=id))
    
    article = conn.execute('SELECT * FROM articles WHERE id = ?', (id,)).fetchone()
    conn.close()
    
    if not article:
        flash('Article not found.')
        return redirect(url_for('admin.index'))
        
    return render_template('admin/edit_article.html', article=article)

@app.route('/admin/create', methods=['GET', 'POST'])
@login_required
def admin_create_article():
    if request.method == 'POST':
        from slugify import slugify
        
        # Text Fields
        title = request.form.get('title')
        slug = request.form.get('slug') or slugify(title)
        category = request.form.get('category')
        published_at = request.form.get('published_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        source = request.form.get('source')
        source_url = request.form.get('source_url')
        
        gist = request.form.get('gist')
        why_it_matters = request.form.get('why_it_matters')
        bull_case = request.form.get('bull_case')
        bear_case = request.form.get('bear_case')
        deep_analysis = request.form.get('deep_analysis')
        
        image_url = request.form.get('image_url')

        # File Handling Helper
        def handle_file_upload(file_input_name, folder, article_slug):
            file = request.files.get(file_input_name)
            if file and file.filename:
                save_dir = os.path.join(app.static_folder, folder)
                os.makedirs(save_dir, exist_ok=True)
                
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                new_filename = f"{article_slug}_{name[:20]}_{int(time.time())}{ext}"
                
                path = os.path.join(save_dir, new_filename)
                file.save(path)
                return f"/static/{folder}/{new_filename}"
            return None

        # Handle Uploads
        new_image = image_url
        uploaded_image = handle_file_upload('image_file', 'uploads', slug or 'art')
        if uploaded_image:
            new_image = uploaded_image
            
        new_audio_male = handle_file_upload('audio_male_file', 'audio', slug or 'art')
        new_audio_female = handle_file_upload('audio_female_file', 'audio', slug or 'art')

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO articles 
            (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, deep_analysis, source, source_url, published_at, audio_male, audio_female)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (slug, title, new_image, category, gist, why_it_matters, bull_case, bear_case, deep_analysis, source, source_url, published_at, new_audio_male, new_audio_female))
        conn.commit()
        new_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.close()
        
        flash('Article created successfully!')
        return redirect(url_for('admin_edit_article', id=new_id))
    
    return render_template('admin/create_article.html')

@app.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_article(id):
    conn = get_db_connection()
    # Optional: Delete files from disk? Maybe safer to keep for now or implement strict cleanup.
    # For now, just DB delete.
    conn.execute('DELETE FROM articles WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Article deleted.')
    return redirect(url_for('admin.index'))




@app.route('/admin/stock-manager', methods=['GET', 'POST'])
@login_required
def admin_files():
    if request.method == 'POST':
        file = request.files.get('file')
        category = request.form.get('category')
        
        if file and category:
            filename = secure_filename(file.filename)
            save_dir = os.path.join(app.static_folder, 'stock', category)
            os.makedirs(save_dir, exist_ok=True)
            file.save(os.path.join(save_dir, filename))
            flash(f'Uploaded {filename} to {category}')
            
    # List files
    files_map = {}
    
    # 1. Stock images by category
    stock_dir = os.path.join(app.static_folder, 'stock')
    if os.path.exists(stock_dir):
        for cat in sorted(os.listdir(stock_dir)):
            cat_path = os.path.join(stock_dir, cat)
            if os.path.isdir(cat_path):
                f_list = [f for f in os.listdir(cat_path) if not f.startswith('.')]
                if f_list:
                    files_map[cat] = sorted(f_list)
    
    # 2. General Article Uploads
    uploads_dir = os.path.join(app.static_folder, 'uploads')
    if os.path.exists(uploads_dir):
        u_list = [f for f in os.listdir(uploads_dir) if not f.startswith('.')]
        if u_list:
            files_map['Article Uploads'] = sorted(u_list)
                
    return render_template('admin/file_manager.html', files=files_map)


@app.route('/admin/author', methods=['GET', 'POST'])
@login_required
def admin_author():
    conn = get_db_connection()
    # Ensure table (Lazy Migration)
    conn.execute('CREATE TABLE IF NOT EXISTS author_config (id INTEGER PRIMARY KEY, name TEXT, title TEXT, bio TEXT, linkedin TEXT, image TEXT)')
    
    if request.method == 'POST':
        name = request.form.get('name')
        title = request.form.get('title')
        bio = request.form.get('bio')
        linkedin = request.form.get('linkedin')
        
        image_path = request.form.get('current_image')
        file = request.files.get('image_file')
        
        if file and file.filename:
            filename = secure_filename(file.filename)
            ts = int(time.time())
            new_name = f"author_{ts}_{filename}"
            save_path = os.path.join(app.static_folder, 'uploads', new_name)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            file.save(save_path)
            image_path = f"/static/uploads/{new_name}"

        # Upsert
        start = conn.execute('SELECT id FROM author_config LIMIT 1').fetchone()
        if start:
            conn.execute('UPDATE author_config SET name=?, title=?, bio=?, linkedin=?, image=? WHERE id=?', (name, title, bio, linkedin, image_path, start['id']))
        else:
            conn.execute('INSERT INTO author_config (name, title, bio, linkedin, image) VALUES (?, ?, ?, ?, ?)', (name, title, bio, linkedin, image_path))
        conn.commit()
        conn.close()
        flash('Profile settings updated!')
        return redirect(url_for('admin_author'))

    author = conn.execute('SELECT * FROM author_config LIMIT 1').fetchone()
    conn.close()
    
    # Defaults for form view if empty
    if not author:
        author = {
            'name': 'Ali Emre Ozen',
            'title': 'VP, Head of Ad Operations & Analytics',
            'bio': "With 12 years in the programmatic space, I’ve managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I'm now focused on integrating AI and automation to streamline the heavy lifting of digital advertising.",
            'linkedin': 'https://www.linkedin.com/in/emreozen/',
            'image': '/static/emre.jpg'
        }
        
    return render_template('admin/author.html', author=author)



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
        if seconds < 7200: return "Just now"
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
    # 1. Default Author Data
    emre_data = {
        'name': 'Ali Emre Ozen',
        'title': 'VP, Head of Ad Operations & Analytics',
        'bio': "With 12 years in the programmatic space, I’ve managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I'm now focused on integrating AI and automation to streamline the heavy lifting of digital advertising.",
        'linkedin': 'https://www.linkedin.com/in/emreozen/',
        'image': '/static/emre.jpg'
    }

    # 2. Try to load overrides from DB
    try:
        conn = get_db_connection()
        # Ensure table exists
        conn.execute('CREATE TABLE IF NOT EXISTS author_config (id INTEGER PRIMARY KEY, name TEXT, title TEXT, bio TEXT, linkedin TEXT, image TEXT)')
        row = conn.execute('SELECT * FROM author_config LIMIT 1').fetchone()
        conn.close()
        
        if row:
            db_data = dict(row)
            # Only update if fields are not empty
            if db_data.get('name'): emre_data['name'] = db_data['name']
            if db_data.get('title'): emre_data['title'] = db_data['title']
            if db_data.get('bio'): emre_data['bio'] = db_data['bio']
            if db_data.get('linkedin'): emre_data['linkedin'] = db_data['linkedin']
            if db_data.get('image'): emre_data['image'] = db_data['image']
    except:
        pass # DB failure shouldn't break the site
        
    # 3. Final Validation: Ensure Image Exists (Self-Healing)
    current_img = emre_data.get('image', '')
    if current_img.startswith('/'):
        # Construct absolute path to check existence
        # app.static_folder is absolute path to static dir
        # current_img usually starts with /static/
        if current_img.startswith('/static/'):
            rel_path = current_img[8:] # remove /static/
            abs_path = os.path.join(app.static_folder, rel_path)
            
            if not os.path.exists(abs_path):
                # Image missing! Fallback.
                fallback_local = os.path.join(app.static_folder, 'emre.jpg')
                if os.path.exists(fallback_local):
                    emre_data['image'] = '/static/emre.jpg'
                else:
                    emre_data['image'] = "https://ui-avatars.com/api/?name=Emre+Ozen&size=512&background=2563eb&color=fff"
    
    # Helper for categories (unchanged)

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
        'config_web3forms_key': os.getenv('WEB3FORMS_ACCESS_KEY'),
        'q': request.args.get('q', ''),
        'emre': emre_data,
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
            carousel = conn.execute('SELECT * FROM articles ORDER BY published_at DESC, id DESC LIMIT 10').fetchall()
            grid = conn.execute('SELECT * FROM articles ORDER BY published_at DESC, id DESC LIMIT ? OFFSET 10', (ITEMS_PER_PAGE,)).fetchall()
            total_arts_count = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            total_arts = max(0, total_arts_count - 10)
        else:
            db_offset = 10 + ((page - 1) * ITEMS_PER_PAGE)
            grid = conn.execute('SELECT * FROM articles ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', (ITEMS_PER_PAGE, db_offset)).fetchall()
            carousel = []
            total_arts_count = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            total_arts = max(0, total_arts_count - 10)

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
    
    # GenUI Token Parsing
    try: d['design_tokens'] = json.loads(art['design_tokens'])
    except: d['design_tokens'] = {}
    
    # SEO Internal Linking: Fetch 3 Related Articles (Same Category)
    conn = get_db_connection()
    related = conn.execute('''
        SELECT title, slug, image, category, published_at 
        FROM articles 
        WHERE category = ? AND id != ? 
        ORDER BY published_at DESC LIMIT 3
    ''', (d['category'], d['id'])).fetchall()
    conn.close()
    
    related_articles = []
    for r in related:
        rd = dict(r)
        # Ensure image path is correct for frontend
        if rd['image'] and not rd['image'].startswith('http') and not rd['image'].startswith('/'):
             rd['image'] = '/' + rd['image']
        related_articles.append(rd)

    return render_template('article.html', article=d, related_articles=related_articles)

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/contact')
def contact(): return render_template('contact.html')

@app.route('/privacy')
def privacy(): return render_template('privacy.html')

@app.route('/impressum')
def impressum(): return render_template('impressum.html')

@app.route('/thank-you')
def thank_you_page():
    return render_template('thank_you.html')

@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form.get('email', '').strip()
    if not email:
        flash("Please provide a valid email address.")
        return redirect(request.referrer or '/')
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO subscribers (email) VALUES (?)', (email,))
        conn.commit()
        # Success: Redirect to dedicated Thank You page
        conn.close()
        return redirect(url_for('thank_you_page'))
        
    except sqlite3.IntegrityError:
        # Already subscribed: Still redirect to Thank You page for good UX (treat as success)
        conn.close()
        return redirect(url_for('thank_you_page'))
        
    except Exception as e:
        conn.close()
        flash("Neural link failed. Please try again later.")
        return redirect(request.referrer or '/')


# Lab routes defined below using file-based storage


@app.after_request
def add_header(r):
    r.headers['Cache-Control'] = 'no-store'
    return r

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.png')

@app.route('/sitemap.xml')
def sitemap():
    """Generate XML sitemap for search engines"""
    conn = get_db_connection()
    # Get articles
    articles = conn.execute('SELECT slug, published_at FROM articles ORDER BY published_at DESC').fetchall()
    # Get blog posts
    blog_posts = get_combined_lab_posts()
    # Get categories for indexing
    categories = conn.execute('SELECT category FROM articles WHERE category IS NOT NULL GROUP BY category').fetchall()
    conn.close()
    
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # Homepage
    xml.append('<url>')
    xml.append('<loc>https://dailyaiwire.news/</loc>')
    xml.append(f'<lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('<changefreq>hourly</changefreq><priority>1.0</priority></url>')
    
    # Lab index
    xml.append('<url><loc>https://dailyaiwire.news/lab</loc>')
    xml.append(f'<lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
    xml.append('<changefreq>weekly</changefreq><priority>0.8</priority></url>')

    # Categories
    for cat in categories:
        xml.append('<url>')
        xml.append(f'<loc>https://dailyaiwire.news/?category={cat["category"]}</loc>')
        xml.append(f'<lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>')
        xml.append('<changefreq>daily</changefreq><priority>0.8</priority></url>')
    
    # Articles
    now = datetime.now()
    for art in articles:
        pub_date = art['published_at'][:10] if art['published_at'] else now.strftime("%Y-%m-%d")
        xml.append(f'<url><loc>https://dailyaiwire.news/article/{art["slug"]}</loc><lastmod>{pub_date}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>')
    
    # Blog posts
    for post in blog_posts:
        pub_date = post['published_at'][:10] if post.get('published_at') else now.strftime("%Y-%m-%d")
        xml.append(f'<url><loc>https://dailyaiwire.news/lab/{post["slug"]}</loc><lastmod>{pub_date}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>')
    
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    """Serve robots.txt"""
    try:
        with open(os.path.join(app.static_folder, 'robots.txt'), 'r') as f:
            content = f.read()
        return Response(content, mimetype='text/plain')
    except:
        return Response("User-agent: *\nAllow: /", mimetype='text/plain')

@app.template_filter('remove_emojis')
def remove_emojis(text):
    if not text: return ""
    return text.encode('ascii', 'ignore').decode('ascii')

@app.route('/rss.xml')
@app.route('/feed')
@app.route('/rss')
def rss_feed():
    conn = get_db_connection()
    articles_db = conn.execute('SELECT * FROM articles WHERE published_at IS NOT NULL ORDER BY id DESC LIMIT 20').fetchall()
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
        except:
            a['pub_date_obj'] = datetime.now()
            a['pub_date_rss'] = formatdate()
        
        # Enclosure
        img_url = a.get('image') or "https://dailyaiwire.news/static/fallbacks/tools_0.jpg"
        if img_url.startswith('/'):
            img_url = f"https://dailyaiwire.news{img_url}"
        a['enclosure_url'] = img_url
        a['enclosure_type'] = "image/jpeg" if "png" not in img_url.lower() else "image/png"
        # Prepare Description
        # Prepare Social Copy for RSS Description
        question = a.get('thought_provoking_question', '')
        gist = a.get('gist', '') or a.get('title', '')
        
        # Hashtags
        hashtags_str = ""
        if a.get('hashtags'):
            try:
                hashtags = json.loads(a['hashtags']) if isinstance(a['hashtags'], str) else a['hashtags']
                if hashtags:
                    hashtags_str = " ".join(hashtags)
            except:
                pass

        # Combine logic: Gist -> Why it Matters -> Question -> Hashtags
        social_parts = []
        if gist:
            social_parts.append(gist)
        
        # Add Why it Matters for length/depth if available
        wim = a.get('why_it_matters', '')
        if wim:
            social_parts.append(f"Why it matters: {wim}")

        # Restore Question
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
            # Handle both formats: 'YYYY-MM-DD' and 'YYYY-MM-DD HH:MM:SS'
            clean_date = p['published_at'].replace('T', ' ').split('.')[0]
            try:
                dt = datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(clean_date[:10], '%Y-%m-%d')
                
            p['pub_date_obj'] = dt
            p['pub_date_rss'] = formatdate(float(dt.timestamp()))
        except:
            # Fallback to a fixed old date rather than 'now' to avoid bumping to top
            p['pub_date_obj'] = datetime(2025, 1, 1)
            p['pub_date_rss'] = formatdate(float(p['pub_date_obj'].timestamp()))

        # Enclosure
        img_url = p.get('image') or "/static/img/default_lab.jpg"
        if img_url.startswith('/'):
            img_url = f"https://dailyaiwire.news{img_url}"
        p['enclosure_url'] = img_url
        p['enclosure_type'] = "image/jpeg"
        p['enclosure_length'] = "0"

        # RSS Description -> Social Copy
        # Format: 🤔 Question \n\n Subtitle \n\n Hashtags
        question = p.get('thought_provoking_question', '')
        subtitle = p.get('subtitle', '')
        hashtags = " ".join(p.get('hashtags', [])) if isinstance(p.get('hashtags'), list) else ""
        
        # RSS Description -> Social Copy (Question removed for LinkedIn)
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
    
    # Limit to 25 items total
    articles = articles[:25]
    
    xml = render_template('rss.xml', articles=articles, build_date=formatdate())
    return Response(xml, mimetype='application/xml')

def get_combined_lab_posts():
    """Fetch posts from both lab_posts.py and the blog_posts DB table"""
    posts = list(get_lab_posts())
    
    conn = get_db_connection()
    try:
        rows = conn.execute('SELECT * FROM blog_posts').fetchall()
        for r in rows:
            posts.append(dict(r))
    except:
        pass # Table might not exist yet
    conn.close()
    
    # Sort by published_at DESC
    posts.sort(key=lambda x: x.get('published_at', ''), reverse=True)
    return posts

@app.route('/lab')
def lab_index():
    posts = get_combined_lab_posts()
    return render_template('lab_index.html', posts=posts)

@app.route('/lab/<slug>')
def lab_post(slug):
    post = get_lab_post(slug)
    
    # If not in file, check DB
    if not post:
        conn = get_db_connection()
        try:
            row = conn.execute('SELECT * FROM blog_posts WHERE slug = ?', (slug,)).fetchone()
            if row: post = dict(row)
        except:
            pass
        conn.close()
        
    if not post:
        abort(404)
    
    return render_template('lab_post.html', post=post)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        env_user = os.getenv('ADMIN_USERNAME', 'admin')
        env_pass = os.getenv('ADMIN_PASSWORD', 'admin')
        
        if username == env_user and password == env_pass:
            user = User(username)
            login_user(user)
            return redirect(url_for('admin.index'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False, port=8000)
