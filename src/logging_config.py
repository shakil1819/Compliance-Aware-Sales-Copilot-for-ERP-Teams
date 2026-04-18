"""
Application logging bootstrap using Loguru.

The logger format includes module, function, and line for easier tracing.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.settings import configs

_CONFIGURED = False
_SETTINGS_LOGGED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    Path(configs.log_dir).mkdir(exist_ok=True)

    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    logger.add(
        sys.stderr,
        level=configs.log_level.upper(),
        format=log_format,
        backtrace=False,
        diagnose=False,
        enqueue=configs.log_enqueue,
    )

    logger.add(
        configs.log_path,
        level=configs.log_level.upper(),
        format=log_format,
        rotation=configs.log_rotation,
        retention=configs.log_retention,
        enqueue=configs.log_enqueue,
        backtrace=False,
        diagnose=False,
    )

    _CONFIGURED = True
    log_loaded_environment()


def log_loaded_environment() -> None:
    global _SETTINGS_LOGGED
    if _SETTINGS_LOGGED:
        return

    logger.info("Loaded environment-backed configuration")
    for key, value in configs.masked_environment_snapshot().items():
        logger.info("Config {}={}", key, value)
    _SETTINGS_LOGGED = True


setup_logging()

__all__ = ["logger", "setup_logging"]
