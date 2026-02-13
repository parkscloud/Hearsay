"""Configure file + console logging."""

import logging
import sys
from datetime import datetime

from hearsay.constants import APP_NAME
from hearsay.utils.paths import get_log_dir


def setup_logging(level: int = logging.INFO) -> None:
    """Set up logging to console and a daily log file."""
    log_dir = get_log_dir()
    log_file = log_dir / f"{APP_NAME.lower()}_{datetime.now():%Y-%m-%d}.log"

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(file_handler)

    logging.getLogger(__name__).info("Logging initialized: %s", log_file)
