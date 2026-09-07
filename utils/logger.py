"""
ALEX — Logging System
Provides colored console output and optional file logging.
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Force Windows console to UTF-8 before importing colorama
if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except AttributeError:
        pass

from colorama import Fore, Style, init as colorama_init

# Initialize colorama
colorama_init(autoreset=True, strip=False)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""

    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    ICONS = {
        logging.DEBUG:    "[DBG]",
        logging.INFO:     "[INF]",
        logging.WARNING:  "[WRN]",
        logging.ERROR:    "[ERR]",
        logging.CRITICAL: "[CRT]",
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, Fore.WHITE)
        icon = self.ICONS.get(record.levelno, "")
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        module = record.module[:12].ljust(12)

        formatted = (
            f"{Fore.WHITE}{Style.DIM}{timestamp}{Style.RESET_ALL} "
            f"{icon} {color}{record.levelname:<8}{Style.RESET_ALL} "
            f"{Fore.BLUE}{module}{Style.RESET_ALL} "
            f"{color}{record.getMessage()}{Style.RESET_ALL}"
        )
        return formatted


def setup_logger(
    name: str = "alex",
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: Path | None = None,
) -> logging.Logger:
    """
    Set up and return a configured logger.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to also write logs to a file
        log_dir: Directory for log files

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler — use sys.stdout which is already UTF-8 wrapped above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # File handler (plain text, no colors)
    if log_to_file:
        if log_dir is None:
            log_dir = Path(__file__).parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"alex_{datetime.now().strftime('%Y-%m-%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(module)-12s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    return logger


# Global logger instance
log = setup_logger()
