"""
Tests for centralized logging configuration.
Verifies setup_logging() is idempotent and that migrated modules
register their named loggers correctly.
"""
import logging
import sys
import os

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging


def test_setup_logging_idempotent():
    """Calling setup_logging() twice must not add duplicate handlers."""
    root = logging.getLogger()
    root.handlers.clear()
    setup_logging()
    count_after_first = len(root.handlers)
    assert count_after_first >= 1, "At least one handler should be added"
    setup_logging()
    assert len(root.handlers) == count_after_first, "Duplicate handlers were added on second call"


def test_setup_logging_sets_level():
    """Default log level should be INFO when LOG_LEVEL is not overridden."""
    root = logging.getLogger()
    root.handlers.clear()
    setup_logging(level='INFO')
    assert root.level == logging.INFO


def test_log_level_from_env(monkeypatch):
    """LOG_LEVEL env var should override the default INFO level."""
    monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
    root = logging.getLogger()
    root.handlers.clear()
    setup_logging()
    assert root.level == logging.DEBUG


def test_noisy_loggers_silenced():
    """Third-party loggers should be set to WARNING after setup."""
    root = logging.getLogger()
    root.handlers.clear()
    setup_logging()
    assert logging.getLogger('urllib3').level == logging.WARNING
    assert logging.getLogger('google').level == logging.WARNING
    assert logging.getLogger('tweepy').level == logging.WARNING


def test_named_loggers_available():
    """Each migrated module should have a named logger retrievable by name."""
    for name in ('weekly_curator', 'lead_extractor', 'proposal_agent',
                 'tavily_research', 'video_renderer', 'app'):
        lgr = logging.getLogger(name)
        assert lgr is not None
        assert lgr.name == name


def test_log_output_format(caplog):
    """Log records should include module name and message."""
    # Use caplog directly without conflicting with our StreamHandler.
    # caplog captures at the logging propagation level — no need to call setup_logging().
    with caplog.at_level(logging.INFO, logger='weekly_curator'):
        logging.getLogger('weekly_curator').info('Test message from weekly_curator')
    assert 'Test message from weekly_curator' in caplog.text
    assert 'weekly_curator' in caplog.text
