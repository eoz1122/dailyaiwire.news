"""
Auth routes — DailyAIWire.news
Login, logout, user management, and Flask-Login setup.
"""
import os
import sqlite3
import logging
import logging.handlers
import time
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import limiter
from db import get_db_connection

logger = logging.getLogger('auth')

# F-21: Dedicated auth audit log — always writes to file regardless of LOG_TO_FILE
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(_log_dir, exist_ok=True)
_auth_handler = logging.handlers.RotatingFileHandler(
    os.path.join(_log_dir, 'auth_audit.log'),
    maxBytes=2 * 1024 * 1024,
    backupCount=5,
    encoding='utf-8'
)
_auth_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S'))
_auth_handler.setLevel(logging.INFO)
logger.addHandler(_auth_handler)

auth_bp = Blueprint('auth', __name__)


# --- Failed Login Tracker (§4 Brute-Force Protection) ---
class FailedLoginTracker:
    """SQLite-backed tracker: locks a username after MAX_ATTEMPTS failures for LOCKOUT_SECONDS.
    Persists across Gunicorn worker restarts and is shared across all workers (F-11)."""

    MAX_ATTEMPTS = 5
    LOCKOUT_SECONDS = 15 * 60  # 15 minutes

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        try:
            conn = get_db_connection()
            conn.execute('''CREATE TABLE IF NOT EXISTS failed_logins (
                username TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                first_at REAL,
                locked_until REAL DEFAULT 0
            )''')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to create failed_logins table: %s", e)

    def is_locked(self, username):
        try:
            conn = get_db_connection()
            row = conn.execute('SELECT locked_until FROM failed_logins WHERE username = ?', (username,)).fetchone()
            conn.close()
            if not row:
                return False
            if row['locked_until'] > time.time():
                return True
            # Lockout expired — reset
            if row['locked_until'] > 0:
                self.reset(username)
            return False
        except Exception:
            return False

    def record_failure(self, username):
        now = time.time()
        try:
            conn = get_db_connection()
            row = conn.execute('SELECT count FROM failed_logins WHERE username = ?', (username,)).fetchone()
            if row:
                new_count = row['count'] + 1
                locked_until = (now + self.LOCKOUT_SECONDS) if new_count >= self.MAX_ATTEMPTS else 0
                conn.execute('UPDATE failed_logins SET count = ?, locked_until = ? WHERE username = ?',
                             (new_count, locked_until, username))
            else:
                new_count = 1
                locked_until = 0
                conn.execute('INSERT INTO failed_logins (username, count, first_at, locked_until) VALUES (?, ?, ?, ?)',
                             (username, 1, now, 0))
            conn.commit()
            conn.close()
            logger.warning("Failed login attempt %d for user '%s' from %s",
                            new_count, username, request.remote_addr)
            if new_count >= self.MAX_ATTEMPTS:
                logger.warning("Account '%s' locked for %d minutes after %d failures",
                                username, self.LOCKOUT_SECONDS // 60, new_count)
        except Exception as e:
            logger.error("Error recording login failure: %s", e)

    def reset(self, username):
        try:
            conn = get_db_connection()
            conn.execute('DELETE FROM failed_logins WHERE username = ?', (username,))
            conn.commit()
            conn.close()
        except Exception:
            pass


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
            return redirect(url_for('admin.index'), code=303)
        else:
            _login_tracker.record_failure(username)
            flash('Invalid credentials', 'error')
    return render_template('login.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    logger.info("User '%s' logged out from %s", current_user.username if current_user.is_authenticated else 'unknown', request.remote_addr)
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
        logger.error("Error creating user: %s", e, exc_info=True)
        flash('An error occurred while creating the user.', 'error')

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
