"""Timestamp and duration formatting for transcripts."""

from __future__ import annotations

from datetime import datetime


def format_timestamp(seconds: float) -> str:
    """Format seconds into H:MM:SS or M:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_duration(seconds: float) -> str:
    """Format a total duration like '1h 23m' or '5m 30s'."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def make_title(prefix: str = "Transcript") -> str:
    """Generate a transcript title with current date/time."""
    now = datetime.now()
    return f"{prefix} - {now:%Y-%m-%d %H:%M}"
