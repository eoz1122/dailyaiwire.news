"""
Auth routes — DailyAIWire.news
Login, logout, user management, and Flask-Login setup.
"""
import sqlite3
import logging
import time
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import limiter
from db import get_db_connection

logger = logging.getLogger('auth')

auth_bp = Blueprint('auth', __name__)


# --- Failed Login Tracker (§4 Brute-Force Protection) ---
class FailedLoginTracker:
    """In-memory tracker: locks a username after MAX_ATTEMPTS failures for LOCKOUT_SECONDS."""

    MAX_ATTEMPTS = 5
    LOCKOUT_SECONDS = 15 * 60  # 15 minutes

    def __init__(self):
        self._attempts = {}  # {username: {"count": int, "first_at": float, "locked_until": float}}

    def is_locked(self, username):
        entry = self._attempts.get(username)
        if not entry:
            return False
        if entry.get("locked_until", 0) > time.time():
            return True
        # Lockout expired — reset
        if entry.get("locked_until"):
            del self._attempts[username]
        return False

    def record_failure(self, username):
        now = time.time()
        entry = self._attempts.get(username, {"count": 0, "first_at": now})
        entry["count"] += 1
        logger.warning("Failed login attempt %d for user '%s' from %s",
                        entry["count"], username, request.remote_addr)
        if entry["count"] >= self.MAX_ATTEMPTS:
            entry["locked_until"] = now + self.LOCKOUT_SECONDS
            logger.warning("Account '%s' locked for %d minutes after %d failures",
                            username, self.LOCKOUT_SECONDS // 60, entry["count"])
        self._attempts[username] = entry

    def reset(self, username):
        self._attempts.pop(username, None)


_login_tracker = FailedLoginTracker()


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
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if _login_tracker.is_locked(username):
            logger.warning("Login attempt on locked account '%s' from %s",
                            username, request.remote_addr)
            flash('Account temporarily locked. Try again later.', 'error')
            return render_template('login.html'), 429

        conn = get_db_connection()
        user_row = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user_row and check_password_hash(user_row['password_hash'], password):
            _login_tracker.reset(username)
            user = User(id=user_row['id'], username=user_row['username'])
            login_user(user)
            logger.info("Successful login for user '%s' from %s", username, request.remote_addr)
            return redirect(url_for('admin.index'))
        else:
            _login_tracker.record_failure(username)
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
