"""
app/utils/logger.py
────────────────────
Loguru-based logging configuration.
• Coloured console output in development
• JSON-structured file output in production
"""

import sys

from loguru import logger

from app.config import get_settings


def setup_logger() -> None:
    """Configure loguru for the application."""
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Console handler — coloured, human-readable
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler — JSON format for production analysis
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        enqueue=True,  # thread-safe
    )

    logger.info(f"Logger configured — level={settings.log_level}, env={settings.app_env}")


def get_logger(name: str):
    """Return a contextualised logger for the given module name."""
    return logger.bind(module=name)
