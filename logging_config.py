"""
DailyAIWire.news — Centralized Logging Configuration

Replaces ad-hoc print() calls with structured logging.
Import and call setup_logging() once at process startup.

Usage:
    from logging_config import setup_logging
    setup_logging()

    import logging
    logger = logging.getLogger('fetcher')
    logger.info("🚀 Starting fetch cycle")
"""
import os
import logging
import logging.handlers


def setup_logging(level=None):
    """Configure structured logging for the entire application.

    Args:
        level: Override log level. Defaults to LOG_LEVEL env var or INFO.
    """
    log_level = level or os.getenv('LOG_LEVEL', 'INFO').upper()

    fmt = '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))

    # Avoid adding duplicate handlers on re-import
    if root.handlers:
        return

    # Console handler (always on)
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, log_level, logging.INFO))
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console)

    # Optional file handler (enable with LOG_TO_FILE=true in .env)
    if os.getenv('LOG_TO_FILE', '').lower() == 'true':
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'dailyaiwire.log'),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    logging.getLogger('tweepy').setLevel(logging.WARNING)
    logging.getLogger('feedparser').setLevel(logging.WARNING)
