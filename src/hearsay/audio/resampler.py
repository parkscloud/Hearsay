"""Resample audio to 16kHz mono float32 for Whisper."""

from __future__ import annotations

import logging

import numpy as np

from hearsay.constants import CHANNELS, SAMPLE_RATE

log = logging.getLogger(__name__)


def resample(
    audio: np.ndarray,
    orig_sr: int,
    orig_channels: int,
) -> np.ndarray:
    """Convert audio to 16kHz mono float32.

    Args:
        audio: Raw audio as numpy array (int16 or float32).
        orig_sr: Original sample rate.
        orig_channels: Original number of channels.

    Returns:
        float32 numpy array at 16kHz mono, values in [-1, 1].
    """
    # Convert to float32 if needed
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    elif audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    # Downmix to mono if stereo
    if orig_channels > 1:
        audio = audio.reshape(-1, orig_channels).mean(axis=1)

    # Resample if needed
    if orig_sr != SAMPLE_RATE:
        # Simple linear interpolation resampling
        duration = len(audio) / orig_sr
        target_len = int(duration * SAMPLE_RATE)
        indices = np.linspace(0, len(audio) - 1, target_len)
        audio = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    # Clip to valid range
    audio = np.clip(audio, -1.0, 1.0)

    return audio
