"""Detect CUDA GPU availability and recommend model/compute_type."""

from __future__ import annotations

import logging
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


def _vram_gb_from_name(name: str) -> float:
    """Estimate VRAM from GPU name when ctranslate2 doesn't expose memory info."""
    name_lower = name.lower()
    # RTX 40xx series
    if "4090" in name_lower:
        return 24.0
    if "4080" in name_lower:
        return 16.0
    if "4070 ti" in name_lower:
        return 12.0
    if "4070" in name_lower:
        return 12.0
    if "4060 ti" in name_lower:
        return 8.0
    if "4060" in name_lower:
        return 8.0
    # RTX 30xx series
    if "3090" in name_lower:
        return 24.0
    if "3080" in name_lower:
        return 10.0
    if "3070" in name_lower:
        return 8.0
    if "3060 ti" in name_lower:
        return 8.0
    if "3060" in name_lower:
        return 12.0
    if "3050" in name_lower:
        return 8.0
    # RTX 20xx series
    if "2080 ti" in name_lower:
        return 11.0
    if "2080" in name_lower:
        return 8.0
    if "2070" in name_lower:
        return 8.0
    if "2060" in name_lower:
        return 6.0
    return 4.0  # conservative default


def detect_gpu() -> GPUInfo:
    """Detect CUDA GPU via ctranslate2 (same backend faster-whisper uses)."""
    try:
        import ctranslate2

        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0:
            # Try to get GPU name via torch if available; otherwise fall back gracefully
            gpu_name = ""
            vram_gb = 0.0
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    vram_bytes = torch.cuda.get_device_properties(0).total_mem
                    vram_gb = round(vram_bytes / (1024**3), 1)
            except Exception:
                pass

            if not gpu_name:
                # ctranslate2 doesn't expose device names; use a generic label
                gpu_name = f"CUDA Device 0"

            if vram_gb == 0.0:
                vram_gb = _vram_gb_from_name(gpu_name)

            log.info("CUDA GPU found: %s (%.1f GB VRAM)", gpu_name, vram_gb)

            if vram_gb >= 6:
                model = DEFAULT_GPU_MODEL
            elif vram_gb >= 2:
                model = "small.en"
            else:
                model = "tiny.en"

            return GPUInfo(
                cuda_available=True,
                gpu_name=gpu_name,
                vram_gb=vram_gb,
                recommended_model=model,
                recommended_compute=DEFAULT_GPU_COMPUTE,
                recommended_device="cuda",
            )
        log.info("No CUDA devices found via ctranslate2")
    except ImportError:
        log.info("ctranslate2 not installed, assuming CPU-only")
    except Exception:
        log.warning("GPU detection failed", exc_info=True)

    return GPUInfo(
        cuda_available=False,
        gpu_name="",
        vram_gb=0,
        recommended_model=DEFAULT_CPU_MODEL,
        recommended_compute=DEFAULT_CPU_COMPUTE,
        recommended_device="cpu",
    )
