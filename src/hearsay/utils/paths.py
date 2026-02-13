"""Manage %APPDATA%\\Hearsay directory structure."""

import os
from pathlib import Path

from hearsay.constants import APP_NAME


def get_appdata_dir() -> Path:
    """Return the Hearsay directory under %APPDATA%, creating it if needed."""
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    app_dir = base / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> Path:
    """Return path to the config JSON file."""
    return get_appdata_dir() / "config.json"


def get_models_dir() -> Path:
    """Return path to the models cache directory."""
    models_dir = get_appdata_dir() / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def get_log_dir() -> Path:
    """Return path to the logs directory."""
    log_dir = get_appdata_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_default_output_dir() -> Path:
    """Return the default transcripts output directory (Documents\\Hearsay)."""
    docs = Path.home() / "Documents" / APP_NAME
    docs.mkdir(parents=True, exist_ok=True)
    return docs
