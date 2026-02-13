"""Mix two audio streams (system audio + microphone)."""

from __future__ import annotations

import numpy as np


def mix_streams(stream_a: np.ndarray, stream_b: np.ndarray) -> np.ndarray:
    """Mix two mono float32 audio arrays by averaging.

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

    mixed = (stream_a + stream_b) / 2.0
    return np.clip(mixed, -1.0, 1.0).astype(np.float32)
