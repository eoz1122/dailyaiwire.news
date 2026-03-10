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
                os.makedirs(save_dir, exist_ok=True)

                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                new_filename = f"{article_slug}_{name[:20]}_{int(time.time())}{ext}"

                path = os.path.join(save_dir, new_filename)
                file.save(path)
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
                os.makedirs(save_dir, exist_ok=True)

                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                new_filename = f"{article_slug}_{name[:20]}_{int(time.time())}{ext}"

                path = os.path.join(save_dir, new_filename)
                file.save(path)
                return f"/static/{folder}/{new_filename}"
            return None

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
        return redirect(url_for('admin_core.admin_edit_article', id=new_id))

    return render_template('admin/create_article.html')


@admin_core_bp.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_article(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM articles WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Article deleted.')
    return redirect(url_for('admin.index'))


@admin_core_bp.route('/admin/stock-manager', methods=['GET', 'POST'])
@login_required
def admin_files():
    if request.method == 'POST':
        file = request.files.get('file')
        category = request.form.get('category')

        if file and category:
            filename = secure_filename(file.filename)
            save_dir = os.path.join(current_app.static_folder, 'stock', category)
            os.makedirs(save_dir, exist_ok=True)
            file.save(os.path.join(save_dir, filename))
            flash(f'Uploaded {filename} to {category}')

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
            filename = secure_filename(file.filename)
            ts = int(time.time())
            new_name = f"author_{ts}_{filename}"
            save_path = os.path.join(current_app.static_folder, 'uploads', new_name)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            file.save(save_path)
            image_path = f"/static/uploads/{new_name}"

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
