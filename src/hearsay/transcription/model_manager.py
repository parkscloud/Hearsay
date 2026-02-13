"""Download, cache, and list Whisper models via faster-whisper."""

from __future__ import annotations

import logging
from pathlib import Path

from hearsay.constants import MODEL_TABLE
from hearsay.utils.paths import get_models_dir

log = logging.getLogger(__name__)


def list_available_models() -> list[str]:
    """Return all model names from the model table."""
    return list(MODEL_TABLE.keys())


def get_model_info(name: str) -> tuple[str, int, bool] | None:
    """Return (parameters, vram_gb, english_only) for a model, or None."""
    return MODEL_TABLE.get(name)


def is_model_downloaded(name: str) -> bool:
    """Check if a model is already cached locally."""
    model_dir = get_models_dir()
    # faster-whisper stores models in subdirectories named after the model
    # Check for the CTranslate2 model file
    model_path = model_dir / f"models--Systran--faster-whisper-{name}"
    if model_path.exists():
        return True
    # Also check for direct directory naming
    alt_path = model_dir / name
    return alt_path.exists() and any(alt_path.iterdir())


def download_model(
    name: str,
    progress_callback: callable | None = None,
) -> str:
    """Download a model if not cached. Returns the model size string for faster-whisper.

    Args:
        name: Model name (e.g., 'turbo', 'small.en').
        progress_callback: Optional callable(status_text) for progress updates.

    Returns:
        The model name/path string to pass to WhisperModel().
    """
    if name not in MODEL_TABLE:
        raise ValueError(f"Unknown model: {name}")

    if progress_callback:
        progress_callback(f"Preparing model '{name}'...")

    model_dir = get_models_dir()
    log.info("Downloading/loading model '%s' to %s", name, model_dir)

    # faster-whisper downloads models from Hugging Face on first use.
    # We trigger this by importing and constructing the model.
    # The download_root parameter controls where models are cached.
    from faster_whisper import WhisperModel

    if progress_callback:
        progress_callback(f"Downloading '{name}' (this may take a few minutes)...")

    # This will download if not cached
    _model = WhisperModel(
        name,
        device="cpu",
        compute_type="int8",
        download_root=str(model_dir),
    )
    del _model  # Free memory; the real model will be loaded by the engine

    if progress_callback:
        progress_callback(f"Model '{name}' ready!")

    log.info("Model '%s' is ready", name)
    return name
