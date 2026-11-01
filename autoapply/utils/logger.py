"""Rich-based structured logging for AutoApply."""

from __future__ import annotations

import logging
import sys

from rich.console import Console
from rich.logging import RichHandler

_CONFIGURED = False


def _configure_root_logger() -> None:
    """Configure the root logger with Rich formatting (called once)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    console = Console(stderr=True)

    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("weasyprint").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with Rich formatting.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        Configured Logger instance.
    """
    _configure_root_logger()
    return logging.getLogger(name)
