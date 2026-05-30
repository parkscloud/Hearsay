"""Download, cache, and list Whisper models via faster-whisper."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from hearsay.constants import HF_CUSTOM_MODELS, MODEL_TABLE
from hearsay.utils.paths import get_models_dir

log = logging.getLogger(__name__)


def list_available_models() -> list[str]:
    """Return all model names from the model table."""
    return list(MODEL_TABLE.keys())


def get_model_info(name: str) -> tuple[str, int, bool] | None:
    """Return (parameters, vram_gb, english_only) for a model, or None."""
    return MODEL_TABLE.get(name)


def is_hf_custom_model(name: str) -> bool:
    """Return True if this model requires HuggingFace download + CTranslate2 conversion."""
    return name in HF_CUSTOM_MODELS


def get_hf_model_local_path(name: str) -> Path:
    """Return the local CTranslate2 directory path for a custom HF model."""
    return get_models_dir() / f"hf-ct2-{name}"


def resolve_model_path(name: str) -> str:
    """Return the model name or local path string for WhisperModel().

    For standard models, returns the name as-is (faster-whisper handles download).
    For custom HF models, returns the local CTranslate2 directory path.
    """
    if is_hf_custom_model(name):
        return str(get_hf_model_local_path(name))
    return name


def is_model_downloaded(name: str) -> bool:
    """Check if a model is already cached locally."""
    if is_hf_custom_model(name):
        local_path = get_hf_model_local_path(name)
        return local_path.exists() and (local_path / "model.bin").exists()

    model_dir = get_models_dir()
    model_path = model_dir / f"models--Systran--faster-whisper-{name}"
    if model_path.exists():
        return True
    alt_path = model_dir / name
    return alt_path.exists() and any(alt_path.iterdir())


def _get_converter_cmd() -> str:
    """Find the ct2-transformers-converter executable."""
    converter = shutil.which("ct2-transformers-converter")
    if converter:
        return converter

    import site
    candidate_dirs: list[Path] = [Path(sys.executable).parent]

    # pip --user installs scripts under {userbase}/PythonXY/Scripts on Windows
    user_base = Path(site.getuserbase())
    for child in user_base.iterdir() if user_base.exists() else []:
        if child.is_dir() and child.name.startswith("Python"):
            candidate_dirs.append(child / "Scripts")
    candidate_dirs.append(user_base / "Scripts")
    candidate_dirs.append(user_base / "bin")

    for d in candidate_dirs:
        for exe_name in ["ct2-transformers-converter", "ct2-transformers-converter.exe"]:
            p = d / exe_name
            if p.exists():
                return str(p)

    raise RuntimeError(
        "ct2-transformers-converter not found.\n"
        "Install required packages:\n"
        "  pip install ctranslate2 transformers torch"
    )


def _download_and_convert_hf_model(
    name: str,
    progress_callback: callable | None = None,
) -> None:
    """Download a HuggingFace Whisper model and convert it to CTranslate2 format."""
    info = HF_CUSTOM_MODELS[name]
    repo_id = info["repo_id"]
    local_path = get_hf_model_local_path(name)

    log.info("Downloading and converting HF model '%s' -> %s", repo_id, local_path)

    try:
        converter = _get_converter_cmd()
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc

    local_path.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(f"Downloading '{repo_id}' from HuggingFace...")

    result = subprocess.run(
        [
            converter,
            "--model", repo_id,
            "--output_dir", str(local_path),
            "--quantization", "int8",
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        shutil.rmtree(local_path, ignore_errors=True)
        stderr_tail = result.stderr[-600:] if result.stderr else "(no output)"
        raise RuntimeError(
            f"CTranslate2 conversion failed for '{repo_id}':\n{stderr_tail}\n\n"
            "Make sure torch is installed: pip install torch"
        )

    log.info("HF model '%s' converted successfully to %s", repo_id, local_path)

    if progress_callback:
        progress_callback(f"Model '{name}' ready!")


def download_model(
    name: str,
    progress_callback: callable | None = None,
) -> str:
    """Download (and convert if needed) a model. Returns model path/name for WhisperModel().

    Args:
        name: Model name from MODEL_TABLE.
        progress_callback: Optional callable(status_text) for progress updates.

    Returns:
        The model name or local path string to pass to WhisperModel().
    """
    if name not in MODEL_TABLE:
        raise ValueError(f"Unknown model: {name}")

    if is_hf_custom_model(name):
        if not is_model_downloaded(name):
            if progress_callback:
                progress_callback(f"Converting '{name}' to CTranslate2 format (this may take several minutes)...")
            _download_and_convert_hf_model(name, progress_callback)
        elif progress_callback:
            progress_callback(f"Model '{name}' already converted.")
        return str(get_hf_model_local_path(name))

    # Standard faster-whisper model
    if progress_callback:
        progress_callback(f"Preparing model '{name}'...")

    model_dir = get_models_dir()
    log.info("Downloading/loading model '%s' to %s", name, model_dir)

    from faster_whisper import WhisperModel

    if progress_callback:
        progress_callback(f"Downloading '{name}' (this may take a few minutes)...")

    _model = WhisperModel(
        name,
        device="cpu",
        compute_type="int8",
        download_root=str(model_dir),
    )
    del _model

    if progress_callback:
        progress_callback(f"Model '{name}' ready!")

    log.info("Model '%s' is ready", name)
    return name
