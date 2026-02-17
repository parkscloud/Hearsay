"""Mix two audio streams (system audio + microphone)."""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

# RMS level each stream is normalised to before mixing.
# 0.1 ≈ −20 dBFS — loud enough for Whisper, with headroom to spare.
_TARGET_RMS = 0.1

# Streams quieter than this are considered silence and left untouched
# to avoid amplifying noise.
_NOISE_FLOOR = 1e-4


def mix_streams(stream_a: np.ndarray, stream_b: np.ndarray) -> np.ndarray:
    """Mix two mono float32 audio arrays with RMS normalisation.

    Each stream is independently normalised to the same RMS level before
    summing so that a quiet microphone is not drowned out by loud system
    audio (or vice-versa).  Streams below the noise floor are left as-is.

    Both inputs should already be 16kHz mono float32.
    If lengths differ, the shorter one is zero-padded.
    """
    len_a, len_b = len(stream_a), len(stream_b)
    if len_a != len_b:
        max_len = max(len_a, len_b)
        if len_a < max_len:
            stream_a = np.pad(stream_a, (0, max_len - len_a))
        else:
            stream_b = np.pad(stream_b, (0, max_len - len_b))

    rms_a = float(np.sqrt(np.mean(stream_a ** 2)))
    rms_b = float(np.sqrt(np.mean(stream_b ** 2)))
    log.debug("Pre-mix RMS: stream_a=%.5f, stream_b=%.5f", rms_a, rms_b)

    if rms_a > _NOISE_FLOOR:
        stream_a = stream_a * (_TARGET_RMS / rms_a)
    if rms_b > _NOISE_FLOOR:
        stream_b = stream_b * (_TARGET_RMS / rms_b)

    mixed = (stream_a + stream_b) / 2.0
    return np.clip(mixed, -1.0, 1.0).astype(np.float32)
