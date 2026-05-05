"""
Admin Core routes — DailyAIWire.news
Article CRUD, file manager, and author profile.
"""
import os
import time
import json
import sqlite3
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename

from db import get_db_connection

admin_core_bp = Blueprint('admin_core', __name__)

IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg'}
STOCK_CATEGORIES = {
    'Business', 'Technology', 'Policy', 'Science', 'Tools', 'Security',
    'Finance', 'Health', 'Energy', 'LLMs', 'Robotics', 'Society', 'AI Agents',
}

import logging
logger = logging.getLogger('admin_core')


def _validate_upload_extension(filename, allowed_extensions):
    secure_name = secure_filename(filename or "")
    _, ext = os.path.splitext(secure_name)
    cleaned_ext = ext.lower().lstrip('.')
    if not cleaned_ext or cleaned_ext not in allowed_extensions:
        raise ValueError(f"File type {ext or '(missing extension)'} not allowed.")
    return secure_name, ext.lower()


def _save_uploaded_file(file_storage, save_dir, new_filename, allowed_extensions):
    secure_name, _ = _validate_upload_extension(file_storage.filename, allowed_extensions)
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, new_filename)
    file_storage.save(path)
    return secure_name


@admin_core_bp.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_edit_article(id):
    conn = get_db_connection()
    if request.method == 'POST':
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

        def handle_file_upload(file_input_name, folder, article_slug):
            file = request.files.get(file_input_name)
            if file and file.filename:
                save_dir = os.path.join(current_app.static_folder, folder)
                filename, ext = _validate_upload_extension(
                    file.filename,
                    IMAGE_EXTENSIONS if folder == 'uploads' else AUDIO_EXTENSIONS,
                )
                name, _ = os.path.splitext(filename)
                new_filename = f"{article_slug}_{name[:20]}_{int(time.time())}{ext}"
                _save_uploaded_file(
                    file,
                    save_dir,
                    new_filename,
                    IMAGE_EXTENSIONS if folder == 'uploads' else AUDIO_EXTENSIONS,
                )
                return f"/static/{folder}/{new_filename}"
            return None

        current = conn.execute('SELECT image, audio_male, audio_female FROM articles WHERE id=?', (id,)).fetchone()

        new_image = current['image']
        new_audio_male = current['audio_male']
        new_audio_female = current['audio_female']

        if request.form.get('delete_image'):
            new_image = None
        if request.form.get('delete_audio_male'):
            new_audio_male = None
        if request.form.get('delete_audio_female'):
            new_audio_female = None

        try:
            uploaded_image = handle_file_upload('image_file', 'uploads', slug or 'art')
            if uploaded_image:
                new_image = uploaded_image
            elif image_url:
                new_image = image_url

            uploaded_male = handle_file_upload('audio_male_file', 'audio', slug or 'art')
            if uploaded_male:
                new_audio_male = uploaded_male

            uploaded_female = handle_file_upload('audio_female_file', 'audio', slug or 'art')
            if uploaded_female:
                new_audio_female = uploaded_female
        except ValueError as e:
            conn.close()
            flash(str(e), 'error')
            return redirect(url_for('admin_core.admin_edit_article', id=id))

        try:
            conn.execute('''
                UPDATE articles
                SET title = ?, slug = ?, category = ?, published_at = ?, source = ?, source_url = ?,
                    gist = ?, why_it_matters = ?, bull_case = ?, bear_case = ?, deep_analysis = ?,
                    image = ?, audio_male = ?, audio_female = ?
                WHERE id = ?
            ''', (title, slug, category, published_at, source, source_url, gist, why_it_matters, bull_case, bear_case, deep_analysis,
                  new_image, new_audio_male, new_audio_female, id))
            conn.commit()
            flash('Article updated successfully!')
        except sqlite3.IntegrityError:
            flash('Error: An article with this slug already exists.', 'error')
        except Exception as e:
            logger.error("Article update error: %s", e, exc_info=True)
            flash('An error occurred while updating the article.', 'error')
        finally:
            conn.close()
        return redirect(url_for('admin_core.admin_edit_article', id=id))

    article = conn.execute('SELECT * FROM articles WHERE id = ?', (id,)).fetchone()
    conn.close()

    if not article:
        flash('Article not found.')
        return redirect(url_for('admin.index'))

    return render_template('admin/edit_article.html', article=article)


@admin_core_bp.route('/admin/create', methods=['GET', 'POST'])
@login_required
def admin_create_article():
    if request.method == 'POST':
        from slugify import slugify

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

        def handle_file_upload(file_input_name, folder, article_slug):
            file = request.files.get(file_input_name)
            if file and file.filename:
                save_dir = os.path.join(current_app.static_folder, folder)
                filename, ext = _validate_upload_extension(
                    file.filename,
                    IMAGE_EXTENSIONS if folder == 'uploads' else AUDIO_EXTENSIONS,
                )
                name, _ = os.path.splitext(filename)
                new_filename = f"{article_slug}_{name[:20]}_{int(time.time())}{ext}"
                _save_uploaded_file(
                    file,
                    save_dir,
                    new_filename,
                    IMAGE_EXTENSIONS if folder == 'uploads' else AUDIO_EXTENSIONS,
                )
                return f"/static/{folder}/{new_filename}"
            return None

        try:
            new_image = image_url
            uploaded_image = handle_file_upload('image_file', 'uploads', slug or 'art')
            if uploaded_image:
                new_image = uploaded_image

            new_audio_male = handle_file_upload('audio_male_file', 'audio', slug or 'art')
            new_audio_female = handle_file_upload('audio_female_file', 'audio', slug or 'art')
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('admin_core.admin_create_article'))

        try:
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
            return redirect(url_for('admin_core.admin_edit_article', id=new_id))
        except sqlite3.IntegrityError:
            flash('Error: An article with this slug or source URL already exists.', 'error')
            return redirect(url_for('admin_core.admin_create_article'))
        except Exception as e:
            logger.error("Article creation error: %s", e, exc_info=True)
            flash('An error occurred while creating the article.', 'error')
            return redirect(url_for('admin_core.admin_create_article'))

    return render_template('admin/create_article.html')


@admin_core_bp.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_article(id):
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM articles WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        flash('Article deleted.')
    except Exception as e:
        flash(f'Error deleting article: {e}', 'error')
    return redirect(url_for('admin.index'))


@admin_core_bp.route('/admin/stock-manager', methods=['GET', 'POST'])
@login_required
def admin_files():
    if request.method == 'POST':
        file = request.files.get('file')
        category = request.form.get('category')

        if file and category:
            try:
                if category not in STOCK_CATEGORIES:
                    raise ValueError('Invalid stock category.')
                filename, _ = _validate_upload_extension(file.filename, IMAGE_EXTENSIONS)
                save_dir = os.path.join(current_app.static_folder, 'stock', category)
                _save_uploaded_file(file, save_dir, filename, IMAGE_EXTENSIONS)
                flash(f'Uploaded {filename} to {category}')
            except ValueError as e:
                flash(str(e), 'error')

    files_map = {}

    stock_dir = os.path.join(current_app.static_folder, 'stock')
    if os.path.exists(stock_dir):
        for cat in sorted(os.listdir(stock_dir)):
            cat_path = os.path.join(stock_dir, cat)
            if os.path.isdir(cat_path):
                f_list = [f for f in os.listdir(cat_path) if not f.startswith('.')]
                if f_list:
                    files_map[cat] = sorted(f_list)

    uploads_dir = os.path.join(current_app.static_folder, 'uploads')
    if os.path.exists(uploads_dir):
        u_list = [f for f in os.listdir(uploads_dir) if not f.startswith('.')]
        if u_list:
            files_map['Article Uploads'] = sorted(u_list)

    return render_template('admin/file_manager.html', files=files_map)


@admin_core_bp.route('/admin/author', methods=['GET', 'POST'])
@login_required
def admin_author():
    conn = get_db_connection()
    conn.execute('CREATE TABLE IF NOT EXISTS author_config (id INTEGER PRIMARY KEY, name TEXT, title TEXT, bio TEXT, linkedin TEXT, image TEXT)')

    if request.method == 'POST':
        name = request.form.get('name')
        title = request.form.get('title')
        bio = request.form.get('bio')
        linkedin = request.form.get('linkedin')

        image_path = request.form.get('current_image')
        file = request.files.get('image_file')

        if file and file.filename:
            try:
                filename, _ = _validate_upload_extension(file.filename, IMAGE_EXTENSIONS)
                ts = int(time.time())
                new_name = f"author_{ts}_{filename}"
                save_dir = os.path.join(current_app.static_folder, 'uploads')
                _save_uploaded_file(file, save_dir, new_name, IMAGE_EXTENSIONS)
                image_path = f"/static/uploads/{new_name}"
            except ValueError as e:
                conn.close()
                flash(str(e), 'error')
                return redirect(url_for('admin_core.admin_author'))

        start = conn.execute('SELECT id FROM author_config LIMIT 1').fetchone()
        if start:
            conn.execute('UPDATE author_config SET name=?, title=?, bio=?, linkedin=?, image=? WHERE id=?', (name, title, bio, linkedin, image_path, start['id']))
        else:
            conn.execute('INSERT INTO author_config (name, title, bio, linkedin, image) VALUES (?, ?, ?, ?, ?)', (name, title, bio, linkedin, image_path))
        conn.commit()
        conn.close()
        flash('Profile settings updated!')
        return redirect(url_for('admin_core.admin_author'))

    author = conn.execute('SELECT * FROM author_config LIMIT 1').fetchone()
    conn.close()

    if not author:
        author = {
            'name': 'Ali Emre Ozen',
            'title': 'VP, Head of Ad Operations & Analytics',
            'bio': "With 12 years in the programmatic space, I've managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I'm now focused on integrating AI and automation to streamline the heavy lifting of digital advertising.",
            'linkedin': 'https://www.linkedin.com/in/emreozen/',
            'image': '/static/emre.jpg'
        }

    return render_template('admin/author.html', author=author)
