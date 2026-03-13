"""
Admin Content routes — DailyAIWire.news
Newsletters, editorials, social queue, audio/video generation, subscribers.
"""
import os
import json
import re
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required

from db import get_db_connection
from budget_tracker import BudgetTracker

admin_content_bp = Blueprint('admin_content', __name__)


def _slugify(text):
    """Simple slugify for editorial titles."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


# --- Subscribers ---

@admin_content_bp.route('/admin/subscribers')
@login_required
def admin_subscribers():
    conn = get_db_connection()
    subscribers = conn.execute('SELECT * FROM subscribers ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/subscribers.html', subscribers=subscribers)


@admin_content_bp.route('/admin/subscribers/delete/<int:id>', methods=['POST'])
@login_required
def delete_subscriber(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM subscribers WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Subscriber deleted successfully.')
    return redirect(url_for('admin_content.admin_subscribers'))


# --- Newsletters ---

@admin_content_bp.route('/admin/newsletters')
@login_required
def admin_newsletters():
    conn = get_db_connection()
    newsletters = conn.execute('''
        SELECT n.*,
        (SELECT COUNT(*) FROM newsletter_deliveries WHERE newsletter_id = n.id) as sent_count,
        (SELECT COUNT(*) FROM newsletter_deliveries WHERE newsletter_id = n.id AND status = 'OPENED') as open_count
        FROM newsletters n
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    return render_template('admin/newsletters.html', newsletters=newsletters)


@admin_content_bp.route('/admin/newsletter/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_edit_newsletter(id):
    conn = get_db_connection()
    if request.method == 'POST':
        subject = request.form.get('subject')
        intro_text = request.form.get('intro_text')
        status = request.form.get('status')

        metadata = {}
        for key, value in request.form.items():
            if key.startswith("metadata_"):
                art_id = key.replace("metadata_", "")
                metadata[art_id] = value

        article_metadata_json = json.dumps(metadata)

        conn.execute('UPDATE newsletters SET subject=?, intro_text=?, status=?, article_metadata=? WHERE id=?',
                     (subject, intro_text, status, article_metadata_json, id))
        conn.commit()
        flash("Newsletter updated.")
        return redirect(url_for('admin_content.admin_newsletters'))

    newsletter = conn.execute('SELECT * FROM newsletters WHERE id=?', (id,)).fetchone()
    if not newsletter:
        abort(404)

    try:
        article_ids = json.loads(newsletter['article_ids'])
    except Exception:
        article_ids = []

    articles = []
    if article_ids:
        placeholders = ', '.join(['?'] * len(article_ids))
        articles_raw = conn.execute(f'SELECT id, title, gist FROM articles WHERE id IN ({placeholders})', article_ids).fetchall()
        articles = [dict(a) for a in articles_raw]

    try:
        article_metadata = json.loads(newsletter['article_metadata']) if newsletter['article_metadata'] else {}
    except Exception:
        article_metadata = {}

    conn.close()
    return render_template('admin/edit_newsletter.html', newsletter=newsletter, articles=articles, article_metadata=article_metadata)


@admin_content_bp.route('/admin/newsletter/delete/<int:id>')
@login_required
def admin_delete_newsletter(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM newsletters WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash("Newsletter deleted.")
    return redirect(url_for('admin_content.admin_newsletters'))


@admin_content_bp.route('/admin/newsletter/generate')
@login_required
def admin_generate_newsletter():
    import subprocess
    import sys
    try:
        subprocess.Popen([sys.executable, 'weekly_curator.py'], cwd=os.getcwd())
        flash("AI Curation Engine started. Draft will appear in a few seconds.")
    except Exception as e:
        flash(f"Failed to start curation: {e}")

    return redirect(url_for('admin_content.admin_newsletters'))


@admin_content_bp.route('/admin/newsletter/send/<int:id>')
@login_required
def admin_send_newsletter(id):
    from newsletter_sender import send_newsletter
    success = send_newsletter(id)
    if success:
        flash("Signal broadcast successful. Intelligence delivered to subscribers.")
    else:
        flash("Signal broadcast failed. Check logs/API key.")

    return redirect(url_for('admin_content.admin_newsletters'))


@admin_content_bp.route('/admin/newsletter/preview')
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


# --- Editorials ---

@admin_content_bp.route('/admin/editorials')
@login_required
def admin_editorials():
    conn = get_db_connection()
    try:
        posts = conn.execute('SELECT * FROM blog_posts ORDER BY published_at DESC, id DESC').fetchall()
    except Exception:
        posts = []
    conn.close()
    return render_template('admin/editorials.html', posts=posts)


@admin_content_bp.route('/admin/editorial/generate')
@login_required
def admin_generate_opinion():
    """Spawns opinion_generator.py to create a draft opinion piece."""
    import subprocess
    import sys
    try:
        subprocess.Popen([sys.executable, 'opinion_generator.py'], cwd=os.getcwd())
        flash("🧠 Opinion piece generation started. A new DRAFT will appear in ~30 seconds.", "success")
    except Exception as e:
        flash(f"Failed to start opinion generator: {e}", "error")
    return redirect(url_for('admin_content.admin_editorials'))


@admin_content_bp.route('/admin/editorial/edit/<id>', methods=['GET', 'POST'])
@login_required
def admin_edit_editorial(id):
    conn = get_db_connection()

    # Ensure is_published column exists
    try:
        conn.execute('SELECT is_published FROM blog_posts LIMIT 1')
    except Exception:
        conn.execute('ALTER TABLE blog_posts ADD COLUMN is_published BOOLEAN DEFAULT 0')
        conn.commit()

    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        if not slug:
            slug = _slugify(title)

        content = request.form.get('content')
        subtitle = request.form.get('subtitle')
        author_name = request.form.get('author_name', 'Aaron Azadi')
        author_title = request.form.get('author_title', 'The Architect')
        meta_description = request.form.get('meta_description', '')
        action = request.form.get('action', 'save')

        if id == 'new':
            is_published = 1 if action == 'publish' else 0
            pub_at = datetime.now() if is_published else None
            conn.execute('''INSERT INTO blog_posts
                (title, slug, content, subtitle, author_name, author_title,
                 author_linkedin, meta_description, is_published, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (title, slug, content, subtitle, author_name, author_title,
                 'https://www.linkedin.com/in/aliemreozen/',
                 meta_description, is_published, pub_at))
        else:
            if action == 'publish':
                conn.execute('''UPDATE blog_posts SET title=?, slug=?, content=?, subtitle=?,
                    author_name=?, author_title=?, meta_description=?,
                    is_published=1, published_at=COALESCE(published_at, ?) WHERE id=?''',
                    (title, slug, content, subtitle, author_name, author_title,
                     meta_description, datetime.now(), id))
            elif action == 'unpublish':
                conn.execute('''UPDATE blog_posts SET title=?, slug=?, content=?, subtitle=?,
                    author_name=?, author_title=?, meta_description=?,
                    is_published=0, published_at=NULL WHERE id=?''',
                    (title, slug, content, subtitle, author_name, author_title,
                     meta_description, id))
            else:
                conn.execute('''UPDATE blog_posts SET title=?, slug=?, content=?, subtitle=?,
                    author_name=?, author_title=?, meta_description=? WHERE id=?''',
                    (title, slug, content, subtitle, author_name, author_title,
                     meta_description, id))
        conn.commit()
        conn.close()

        if action == 'publish':
            flash('✅ Post published successfully!', 'success')
        elif action == 'unpublish':
            flash('Post unpublished (back to DRAFT).', 'warning')
        else:
            flash('Post saved successfully.')
        return redirect(url_for('admin_content.admin_editorials'))

    post = {}
    if id != 'new':
        try:
            post_row = conn.execute('SELECT * FROM blog_posts WHERE id = ?', (id,)).fetchone()
            if post_row:
                post = dict(post_row)
        except Exception:
            pass

    conn.close()
    return render_template('admin/edit_editorial.html', post=post, id=id)


# --- Social Queue ---

@admin_content_bp.route('/admin/social-queue')
@login_required
def admin_social_queue():
    conn = get_db_connection()
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

    processed = []
    for a in articles:
        d = dict(a)
        if d.get('hashtags'):
            try:
                d['hashtags'] = json.loads(d['hashtags'])
            except Exception:
                d['hashtags'] = []
        else:
            d['hashtags'] = []
        processed.append(d)

    return render_template('admin/social_queue.html', articles=processed)


@admin_content_bp.route('/admin/mark-shared/<int:id>', methods=['POST'])
@login_required
def admin_mark_shared(id):
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE id = ?',
                 (datetime.utcnow().isoformat(), id))
    conn.commit()
    conn.close()
    flash("Article marked as shared. Automation will skip it.")
    return redirect(url_for('admin_content.admin_social_queue'))


# --- Audio / Video Generation ---

@admin_content_bp.route('/admin/generate-video/<int:id>', methods=['POST'])
@login_required
def admin_generate_video(id):
    """Spawns a background thread to generate a LinkedIn Audiogram."""
    import threading
    from maintenance.linkedin_audiogram import generate_audiogram

    def run_gen(aid):
        print(f"🧵 Thread started for Video {aid}")
        generate_audiogram(aid)
        print(f"🏁 Thread finished for Video {aid}")

    thread = threading.Thread(target=run_gen, args=(id,))
    thread.start()

    flash(f"🎬 Video generation started for Article {id}. Check /static/videos/ shortly!", "success")
    return redirect(request.referrer or url_for('admin.index'))


@admin_content_bp.route('/admin/generate-audio/<int:id>', methods=['POST'])
@login_required
def admin_generate_audio(id):
    """Generate audio narration for a specific article."""
    import threading
    from audio_generator import AudioGenerator

    def run_audio_gen(article_id):
        print(f"🎙️ Thread started for Audio {article_id}")
        try:
            conn = get_db_connection()
            article = conn.execute('''
                SELECT slug, title, gist, why_it_matters, bull_case, bear_case,
                       key_details, narration_script
                FROM articles WHERE id = ?
            ''', (article_id,)).fetchone()

            if not article:
                print(f"❌ Article {article_id} not found")
                return

            slug, title, gist, matters, bull, bear, details_json, script = article

            if script and len(script) > 50:
                text_to_read = script
            else:
                try:
                    key_details = json.loads(details_json) if details_json else []
                except Exception:
                    key_details = []
                key_details_text = ". ".join(key_details)
                text_to_read = (
                    f"Intelligence from DailyAIWire dot news. "
                    f"Headline: {title}. "
                    f"The Gist: {gist}. "
                    f"Why It Matters: {matters}. "
                    f"Optimistic Outlook: {bull}. "
                    f"Risk Factors: {bear}. "
                    f"Key Details: {key_details_text}. "
                )

            audio_gen = AudioGenerator()
            male, female = audio_gen.generate_audio_reads(slug, text_to_read)

            if male and female:
                conn.execute(
                    'UPDATE articles SET audio_male = ?, audio_female = ? WHERE id = ?',
                    (male, female, article_id)
                )
                conn.commit()
                print(f"✅ Audio generated for article {article_id}")
            else:
                print(f"❌ Audio generation failed for article {article_id}")

            conn.close()
        except Exception as e:
            print(f"❌ Error generating audio: {e}")

        print(f"🏁 Thread finished for Audio {article_id}")

    thread = threading.Thread(target=run_audio_gen, args=(id,))
    thread.start()

    flash(f"🎙️ Audio generation started for Article {id}. Refresh in 30 seconds!", "success")
    return redirect(request.referrer or url_for('admin.index'))
