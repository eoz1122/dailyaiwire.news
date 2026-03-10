"""
Auth routes — DailyAIWire.news
Login, logout, user management, and Flask-Login setup.
"""
import sqlite3
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db_connection

auth_bp = Blueprint('auth', __name__)


# --- User Model ---
class User(UserMixin):
    def __init__(self, id, username=None):
        self.id = id
        self.username = username


def init_login_manager(app):
    """Initialize Flask-Login on the app. Called from app factory."""
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        user_row = conn.execute('SELECT id, username FROM admins WHERE id = ?', (user_id,)).fetchone()
        conn.close()

        if user_row:
            return User(id=user_row['id'], username=user_row['username'])
        return None

    return login_manager


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        user_row = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user_row and check_password_hash(user_row['password_hash'], password):
            user = User(id=user_row['id'], username=user_row['username'])
            login_user(user)
            return redirect(url_for('admin.index'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('public.index'))


@auth_bp.route('/admin/users')
@login_required
def admin_users():
    """List all admin users."""
    conn = get_db_connection()
    admins = conn.execute('SELECT * FROM admins').fetchall()
    conn.close()
    return render_template('admin/users.html', admins=admins)


@auth_bp.route('/admin/users/add', methods=['POST'])
@login_required
def admin_add_user():
    """Add a new admin user."""
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash('Username and password are required!', 'error')
        return redirect(url_for('auth.admin_users'))

    try:
        conn = get_db_connection()
        p_hash = generate_password_hash(password)
        conn.execute('INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)',
                     (username, p_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        flash(f'Admin {username} created successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Username already exists!', 'error')
    except Exception as e:
        flash(f'Error creating user: {e}', 'error')

    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_user(id):
    """Delete an admin user."""
    if id == current_user.id:
        flash('You cannot delete yourself!', 'error')
        return redirect(url_for('auth.admin_users'))

    conn = get_db_connection()
    conn.execute('DELETE FROM admins WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Admin deleted successfully.', 'success')
    return redirect(url_for('auth.admin_users'))
