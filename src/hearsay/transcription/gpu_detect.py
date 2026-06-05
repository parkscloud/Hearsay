"""Detect CUDA GPU availability and recommend model/compute_type."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from hearsay.constants import (
    DEFAULT_CPU_COMPUTE,
    DEFAULT_CPU_MODEL,
    DEFAULT_GPU_COMPUTE,
    DEFAULT_GPU_MODEL,
)

log = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """GPU detection result."""

    cuda_available: bool
    gpu_name: str
    vram_gb: float
    recommended_model: str
    recommended_compute: str
    recommended_device: str


def detect_gpu() -> GPUInfo:
    """Detect CUDA GPU and return recommendation.
    
    Tries multiple methods:
    1. PyTorch (if installed)
    2. nvidia-smi + ctranslate2 (lightweight fallback)
    """
    # Method 1: PyTorch
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_mem
            vram_gb = vram_bytes / (1024**3)
            return _create_gpu_info(name, vram_gb)
    except (ImportError, Exception):
        pass

    # Method 2: ctranslate2 + nvidia-smi (no torch needed)
    try:
        import ctranslate2  # type: ignore
        if ctranslate2.get_cuda_device_count() > 0:
            # Query name and total memory in MB
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
            result = subprocess.check_output(cmd, encoding="utf-8").strip()
            if result:
                name, vram_mb = result.split(", ")
                vram_gb = float(vram_mb) / 1024
                return _create_gpu_info(name, vram_gb)
    except (ImportError, Exception):
        pass

    return GPUInfo(
        cuda_available=False,
        gpu_name="",
        vram_gb=0,
        recommended_model=DEFAULT_CPU_MODEL,
        recommended_compute=DEFAULT_CPU_COMPUTE,
        recommended_device="cpu",
    )


def _create_gpu_info(name: str, vram_gb: float) -> GPUInfo:
    """Helper to create GPUInfo with recommendations."""
    log.info("CUDA GPU found: %s (%.1f GB VRAM)", name, vram_gb)

    if vram_gb >= 6:
        model = DEFAULT_GPU_MODEL
    elif vram_gb >= 2:
        model = "small.en"
    else:
        model = "tiny.en"

    return GPUInfo(
        cuda_available=True,
        gpu_name=name,
        vram_gb=round(vram_gb, 1),
        recommended_model=model,
        recommended_compute=DEFAULT_GPU_COMPUTE,
        recommended_device="cuda",
    )
