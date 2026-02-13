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


def detect_gpu() -> GPUInfo:
    """Detect CUDA GPU and return recommendation."""
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_mem
            vram_gb = vram_bytes / (1024**3)
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
    except ImportError:
        log.info("PyTorch not installed, assuming CPU-only")
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
