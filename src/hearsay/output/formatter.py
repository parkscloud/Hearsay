"""Timestamp and duration formatting for transcripts."""

from __future__ import annotations

import re
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


# --- Post-processing helpers ---

# Filler words removed for English transcripts (whole-word, case-insensitive)
_FILLER_RE = re.compile(
    r"\b(?:um|uh|er|erm|hmm)\b[,]?",
    re.IGNORECASE,
)


def _remove_fillers(text: str) -> str:
    """Strip filler words (English only)."""
    return _FILLER_RE.sub("", text)


def _remove_duplicate_phrases(text: str) -> str:
    """Collapse adjacent identical 3-8 word sequences to one occurrence."""
    for n in range(8, 2, -1):  # longest first to catch bigger duplicates
        pattern = re.compile(
            r"(\b(?:\S+\s+){" + str(n - 1) + r"}\S+)"  # capture n words
            r"(?:\s+\1)+",  # one or more adjacent repetitions
            re.IGNORECASE,
        )
        text = pattern.sub(r"\1", text)
    return text


def _capitalize_paragraph_starts(text: str) -> str:
    """Uppercase the first letter after each paragraph break."""
    parts = text.split("\n\n")
    return "\n\n".join(
        p[0].upper() + p[1:] if p and p[0].islower() else p
        for p in parts
    )


def _collapse_whitespace(text: str) -> str:
    """Normalize spaces and newlines."""
    # Collapse runs of spaces (not newlines) to a single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ newlines to double newline
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing spaces per line
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


def clean_transcript_text(body: str, language: str = "en") -> str:
    """Run all post-processing cleanup on transcript body text."""
    if language.startswith("en"):
        body = _remove_fillers(body)
    body = _remove_duplicate_phrases(body)
    body = _collapse_whitespace(body)
    body = _capitalize_paragraph_starts(body)
    return body
