"""
Admin Content routes — DailyAIWire.news
Newsletters, editorials, social queue, audio/video generation, subscribers.
"""
import os
import json
import re
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required

from db import get_db_connection
from budget_tracker import BudgetTracker
from services.subscribers import (
    create_confirmation_token,
    ensure_subscribers_schema,
    hash_value,
    record_subscriber_event,
)
import logging

logger = logging.getLogger('admin_content')

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
    ensure_subscribers_schema(conn)
    subscribers = conn.execute('SELECT * FROM subscribers ORDER BY created_at DESC').fetchall()
    status_counts = {
        row['status']: row['count']
        for row in conn.execute(
            'SELECT status, COUNT(*) AS count FROM subscribers GROUP BY status'
        ).fetchall()
    }
    conn.close()
    return render_template(
        'admin/subscribers.html',
        subscribers=subscribers,
        status_counts=status_counts,
    )


@admin_content_bp.route('/admin/subscribers/reconfirm-suspicious', methods=['POST'])
@login_required
def reconfirm_suspicious_subscribers():
    import newsletter_sender

    conn = get_db_connection()
    sent = 0
    failed = 0
    try:
        ensure_subscribers_schema(conn)
        suspicious_subscribers = conn.execute(
            '''
            SELECT id, email
            FROM subscribers
            WHERE status = 'SUSPICIOUS'
            ORDER BY created_at ASC
            '''
        ).fetchall()

        for subscriber in suspicious_subscribers:
            token, token_hash = create_confirmation_token()
            confirmation_url = url_for(
                'public.confirm_subscription',
                token=token,
                _external=True,
                _scheme='https',
            )
            email_sent = newsletter_sender.send_confirmation_email(
                subscriber['email'],
                confirmation_url,
            )
            if email_sent:
                conn.execute(
                    '''
                    UPDATE subscribers
                    SET status = 'PENDING',
                        confirmation_token_hash = ?,
                        confirmed_at = NULL
                    WHERE id = ?
                    ''',
                    (token_hash, subscriber['id']),
                )
                record_subscriber_event(
                    conn,
                    email=subscriber['email'],
                    event_type='reconfirmation_sent',
                    reason='suspicious_batch_reconfirmation',
                    ip_hash=hash_value(request.remote_addr or 'unknown'),
                    user_agent=(request.headers.get('User-Agent') or '')[:500],
                    referrer=(request.referrer or '')[:500],
                    source_path='/admin/subscribers/reconfirm-suspicious',
                )
                sent += 1
            else:
                record_subscriber_event(
                    conn,
                    email=subscriber['email'],
                    event_type='reconfirmation_failed',
                    reason='email_send_failed',
                    ip_hash=hash_value(request.remote_addr or 'unknown'),
                    user_agent=(request.headers.get('User-Agent') or '')[:500],
                    referrer=(request.referrer or '')[:500],
                    source_path='/admin/subscribers/reconfirm-suspicious',
                )
                failed += 1

        conn.commit()
    finally:
        conn.close()

    if sent or failed:
        flash(f'Reconfirmation sent to {sent} suspicious subscribers. Failed: {failed}.')
    else:
        flash('No suspicious subscribers need reconfirmation.')
    return redirect(url_for('admin_content.admin_subscribers'))


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


@admin_content_bp.route('/admin/newsletter/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_newsletter(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM newsletters WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash("Newsletter deleted.")
    return redirect(url_for('admin_content.admin_newsletters'))


@admin_content_bp.route('/admin/newsletter/generate', methods=['POST'])
@login_required
def admin_generate_newsletter():
    import subprocess
    import sys
    try:
        subprocess.Popen([sys.executable, 'weekly_curator.py'], cwd=os.getcwd())
        flash("AI Curation Engine started. Draft will appear in a few seconds.")
    except Exception as e:
        logger.error("Newsletter generation error: %s", e)
        flash("Failed to start curation. Check server logs.")

    return redirect(url_for('admin_content.admin_newsletters'))


@admin_content_bp.route('/admin/newsletter/send/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_send_newsletter(id):
    # GET requests (e.g. direct URL navigation) redirect gracefully
    if request.method == 'GET':
        flash("Use the Send Now button from the newsletters list.", "warning")
        return redirect(url_for('admin_content.admin_newsletters'))

    import threading
    from newsletter_sender import send_newsletter

    def _send():
        try:
            send_newsletter(id)
        except Exception as e:
            logger.error("Background newsletter send error (id=%s): %s", id, e)

    t = threading.Thread(target=_send, daemon=True)
    t.start()

    flash("Signal broadcast initiated. Emails are being delivered in the background.")
    return redirect(url_for('admin_content.admin_newsletters'))


@admin_content_bp.route('/admin/newsletter/preview')
@login_required
def admin_newsletter_preview():
    """Renders the newsletter template with mock data for design review."""
    mock_articles = [
        {
            "id": 101,
            "category": "Artificial Intelligence",
            "title": "Gemini 2.5: The Dawn of True Reasoning Agents",
            "gist": "Google's latest sweep of the Gemini architecture introduces self-correcting logic loops...",
            "slug": "gemini-2.5-reasoning-agents"
        },
        {
            "id": 102,
            "category": "Robotics",
            "title": "Figure 02 Integrates OpenAI Vision for Factory Precision",
            "gist": "The second generation Figure robot now utilizes a specialized vision-language model...",
            "slug": "figure-02-openai-vision"
        },
        {
            "id": 103,
            "category": "Open Source",
            "title": "Llama 4 Release Signals the End of Proprietary Moats",
            "gist": "Meta's upcoming 400B parameter model is rumored to outperform GPT-5...",
            "slug": "llama-4- proprietary-moats"
        }
    ]

    mock_metadata = {
        "101": "This represents a definitive shift away from pure conversational AI towards true autonomous agents, massively lowering the cost of reasoning.",
        # Article 102 will purposefully fall back to gist because it has no metadata
        "103": "Open Source is crossing the rubicon. As parameter counts increase, Meta is commoditizing the model layer, forcing competitors to pivot their moats to data and compute."
    }

    preview_dt = datetime(2026, 4, 26, 18, 0, 0)
    preview_issue = f"W{preview_dt.isocalendar().week:02d} · {preview_dt.year}"

    return render_template('email/briefing.html',
                           subject="[PREVIEW] The Intelligence Briefing: Llama 4 and the Future of Moats",
                           intro_text="This week was a transition from AI as a tool to AI as a teammate. The release of Gemini 2.5 and the rumors surrounding Llama 4 suggest that the scaling laws are still very much in effect, but the 'intelligence' is now moving into the reasoning layer. We are seeing models that don't just predict the next token, but predict the next *intended* outcome.",
                           articles=mock_articles,
                           article_metadata=mock_metadata,
                           newsletter_date_display=preview_dt.strftime("%d %b %Y").upper(),
                           newsletter_issue_label=preview_issue,
                           tracking_pixel_url="")


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


@admin_content_bp.route('/admin/editorial/generate', methods=['GET', 'POST'])
@login_required
def admin_generate_opinion():
    """Spawns opinion_generator.py to create a draft opinion piece."""
    if request.method == 'GET':
        # Graceful redirect when endpoint is visited directly via browser
        return redirect(url_for('admin_content.admin_editorials'))
    import subprocess
    import sys
    try:
        # Use absolute paths so this works correctly from Gunicorn's cwd
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_exe = sys.executable
        script = os.path.join(app_dir, 'opinion_generator.py')
        log_path = os.path.join(app_dir, 'logs', 'opinion_generator.log')
        os.makedirs(os.path.join(app_dir, 'logs'), exist_ok=True)
        with open(log_path, 'a') as log_f:
            subprocess.Popen(
                [python_exe, script],
                cwd=app_dir,
                stdout=log_f,
                stderr=log_f,
            )
        flash("🧠 Opinion piece generation started. A new DRAFT will appear in ~30 seconds.", "success")
    except Exception as e:
        logger.error("Opinion generation error: %s", e)
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
        logger.info("Thread started for Video %s", aid)
        generate_audiogram(aid)
        logger.info("Thread finished for Video %s", aid)

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
        logger.info("Thread started for Audio %s", article_id)
        try:
            conn = get_db_connection()
            article = conn.execute('''
                SELECT slug, title, gist, why_it_matters, bull_case, bear_case,
                       key_details, narration_script
                FROM articles WHERE id = ?
            ''', (article_id,)).fetchone()

            if not article:
                logger.error("Article %s not found", article_id)
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
                logger.info("Audio generated for article %s", article_id)
            else:
                logger.error("Audio generation failed for article %s", article_id)

            conn.close()
        except Exception as e:
            logger.error("Error generating audio: %s", e)

        logger.info("Thread finished for Audio %s", article_id)

    thread = threading.Thread(target=run_audio_gen, args=(id,))
    thread.start()

    flash(f"🎙️ Audio generation started for Article {id}. Refresh in 30 seconds!", "success")
    return redirect(request.referrer or url_for('admin.index'))


# --- Editorial Social Sharing ---

@admin_content_bp.route('/admin/editorial/share/<int:id>', methods=['POST'])
@login_required
def admin_share_editorial(id):
    """Manually post a published editorial to X."""
    platform = request.form.get('platform', '').lower()
    if platform != 'x':
        return jsonify({'ok': False, 'error': 'Invalid platform'}), 400

    conn = get_db_connection()
    try:
        row = conn.execute('SELECT * FROM blog_posts WHERE id = ?', (id,)).fetchone()
    except Exception as e:
        conn.close()
        return jsonify({'ok': False, 'error': str(e)}), 500
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'Editorial not found'}), 404

    post = dict(row)
    if not post.get('is_published'):
        return jsonify({'ok': False, 'error': 'Editorial must be published first'}), 400

    # Map blog_post → SocialDistributor article format
    slug = post['slug']
    article = {
        'seo_slug':                  slug,
        'headline':                  post['title'],
        'gist':                      post.get('gist') or post.get('subtitle') or post.get('meta_description') or '',
        'thought_provoking_question': None,
        'hashtags':                  ['#DailyAIWire', '#AI', '#Opinion'],
        'image':                     post.get('image') or '/static/fallbacks/editorial_0.jpg',
        'source':                    post.get('author_name') or 'DailyAIWire',
        # Editorials live at /lab/<slug>, not /article/<slug>
        '_url_override':             f"https://dailyaiwire.news/lab/{slug}",
    }

    try:
        from social_distributor import SocialDistributor

        sd = SocialDistributor()

        # Patch base URL resolver to use /lab/ path for editorials
        lab_url = f"https://dailyaiwire.news/lab/{slug}"

        if platform == 'x':
            # Temporary monkey-patch to use /lab/ URL
            from url_shortener import shorten
            article_x = dict(article)
            article_x['_short_link'] = shorten(f"{lab_url}?utm_source=twitter&utm_medium=social&utm_campaign=editorial")

            # Override post_to_x behaviour by building tweet text directly
            from helpers import clean_markdown
            import tweepy
            client = tweepy.Client(
                bearer_token=sd.x_bearer_token,
                consumer_key=sd.x_api_key,
                consumer_secret=sd.x_api_secret,
                access_token=sd.x_access_token,
                access_token_secret=sd.x_access_secret,
            )
            gist_clean = clean_markdown(article_x['gist'])
            link = article_x['_short_link']
            tweet_text = f"📝 {article_x['headline']}\n\n{gist_clean[:200]}\n\n🔗 Full Column: {link}\n\n#DailyAIWire #AI #Opinion"
            resp = client.create_tweet(text=tweet_text)
            logger.info("✅ Editorial posted to X! ID: %s", resp.data['id'])
            return jsonify({'ok': True, 'platform': 'x', 'id': resp.data['id']})

    except Exception as e:
        logger.error("❌ Editorial social share error (%s): %s", platform, e)
        return jsonify({'ok': False, 'error': str(e)}), 500
