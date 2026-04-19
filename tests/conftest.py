"""
Pytest configuration — DailyAIWire.news
Shared fixtures for the test suite.
"""
import os
import sys
import sqlite3
import tempfile

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope='session', autouse=True)
def _patch_db(tmp_path_factory):
    """Redirect all DB operations to a temporary SQLite file for test isolation."""
    tmp_db = str(tmp_path_factory.mktemp('data') / 'test_news.db')

    # Patch db.py BEFORE importing app
    import db as db_module
    db_module.DB_PATH = tmp_db

    # Create minimal schema so routes don't crash
    conn = sqlite3.connect(tmp_db)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            image TEXT,
            category TEXT,
            gist TEXT,
            why_it_matters TEXT,
            bull_case TEXT,
            bear_case TEXT,
            key_details TEXT,
            eli5 TEXT,
            deep_analysis TEXT,
            source TEXT,
            source_url TEXT UNIQUE,
            full_json TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            audio_male TEXT,
            audio_female TEXT,
            narration_script TEXT,
            thought_provoking_question TEXT,
            importance_score INTEGER DEFAULT 50,
            original_author TEXT,
            hashtags TEXT,
            shared_on_x BOOLEAN DEFAULT 0,
            shared_at TIMESTAMP,
            is_published INTEGER DEFAULT 1,
            views INTEGER DEFAULT 0,
            audio_plays INTEGER DEFAULT 0,
            design_tokens TEXT,
            compass_score REAL DEFAULT 0.7,
            source_content_hash TEXT,
            ai_model_used TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS blocked_sources (
            domain TEXT PRIMARY KEY,
            reason TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS carousel_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL UNIQUE,
            position INTEGER NOT NULL DEFAULT 0,
            pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            pinned_by TEXT,
            FOREIGN KEY (article_id) REFERENCES articles(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ai_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_type TEXT,
            prompt_text TEXT,
            response_text TEXT,
            cost_estimate REAL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS processing_attempts (
            url TEXT PRIMARY KEY,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS duplicate_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keep_article_id INTEGER NOT NULL,
            keep_title TEXT,
            duplicate_article_id INTEGER NOT NULL,
            duplicate_title TEXT,
            detection_method TEXT NOT NULL,
            confidence_score REAL,
            reason TEXT,
            status TEXT DEFAULT 'PENDING_REVIEW',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            source_url TEXT,
            title TEXT,
            status TEXT DEFAULT 'NEW',
            confidence_score INTEGER DEFAULT 50,
            opportunity_reason TEXT,
            found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS author_config (
            id INTEGER PRIMARY KEY,
            name TEXT,
            title TEXT,
            bio TEXT,
            linkedin TEXT,
            image TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Seed one test article for route tests
    conn.execute('''
        INSERT INTO articles (slug, title, image, category, gist, why_it_matters,
            bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url,
            full_json, published_at, importance_score, is_published, design_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'test-article-slug',
        'Test Article Title',
        '/static/fallbacks/tools_0.jpg',
        'Tools',
        'Test gist content.',
        'This matters because tests.',
        'Upside potential.',
        'Downside risk.',
        '["Fact 1", "Fact 2"]',
        'Explain like I am five.',
        'Deep analysis text goes here with enough content.',
        'Test Source',
        'https://example.com/test-article',
        '{}',
        '2026-03-10T12:00:00',
        75,
        1,
        '{"intensity": "standard", "sentiment_pallet": "techno-optimist", "component_triggers": []}'
    ))

    # Seed a second test article WITH a mermaid diagram for DeepDiagram tests
    conn.execute('''
        INSERT INTO articles (slug, title, image, category, gist, why_it_matters,
            bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url,
            full_json, published_at, importance_score, is_published, design_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'test-article-with-diagram',
        'Test Article With Diagram',
        '/static/fallbacks/tools_0.jpg',
        'Tools',
        'Test gist for diagram article.',
        'Diagrams matter for visualization.',
        'Visual upside.',
        'Complexity risk.',
        '["Fact A", "Fact B"]',
        'A picture is worth a thousand words.',
        'Deep analysis with technical architecture details.',
        'Test Source',
        'https://example.com/test-diagram-article',
        '{"mermaid_diagram": "flowchart LR\\n  A[Input] --> B[Process] --> C[Output]"}',
        '2026-03-10T13:00:00',
        85,
        1,
        '{"intensity": "high", "sentiment_pallet": "techno-optimist", "component_triggers": []}'
    ))

    # Seed a third article with high importance_score for LinkedIn RSS tests
    conn.execute('''
        INSERT INTO articles (slug, title, image, category, gist, why_it_matters,
            bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url,
            full_json, published_at, importance_score, is_published, design_tokens,
            thought_provoking_question, hashtags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'test-linkedin-high-score',
        'High-Score LinkedIn Test Article',
        '/static/fallbacks/tools_0.jpg',
        'Research',
        'A high-importance gist for LinkedIn.',
        'Major research breakthrough.',
        'Massive upside.',
        'Some risk.',
        '["Fact X", "Fact Y"]',
        'Big news explained simply.',
        'Deep analysis of the research.',
        'Test Source',
        'https://example.com/test-linkedin-article',
        '{}',
        '2026-03-10T12:00:00',
        90,
        1,
        '{}',
        'What does this mean for the industry?',
        '["#AI", "#Research"]'
    ))
    conn.commit()
    conn.close()

    yield tmp_db


@pytest.fixture()
def client(_patch_db):
    """Flask test client (unauthenticated)."""
    from app import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False
    with app.test_client() as c:
        yield c


@pytest.fixture()
def auth_client(_patch_db):
    """Flask test client authenticated as admin."""
    from app import app
    from werkzeug.security import generate_password_hash
    import db as db_module

    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    # Ensure test admin exists
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        'INSERT OR IGNORE INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)',
        ('testadmin', generate_password_hash('testpass', method='pbkdf2:sha256'), '2026-01-01 00:00:00')
    )
    conn.commit()
    conn.close()

    with app.test_client() as c:
        c.post('/login', data={'username': 'testadmin', 'password': 'testpass'}, follow_redirects=True)
        yield c
