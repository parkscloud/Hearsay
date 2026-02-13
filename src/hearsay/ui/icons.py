"""Programmatic tray icon generation using Pillow."""

from __future__ import annotations

from PIL import Image, ImageDraw

from hearsay.constants import ICON_COLOR_IDLE, ICON_COLOR_PROCESSING, ICON_COLOR_RECORDING


def _create_icon(color: tuple[int, int, int], size: int = 64) -> Image.Image:
    """Create a simple circular icon with the given color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    # Outer circle
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color + (255,),
    )
    # Inner highlight
    highlight_margin = size // 4
    draw.ellipse(
        [highlight_margin, highlight_margin,
         size - highlight_margin, size - highlight_margin],
        fill=(255, 255, 255, 60),
    )
    return img


def icon_idle() -> Image.Image:
    return _create_icon(ICON_COLOR_IDLE)


def icon_recording() -> Image.Image:
    return _create_icon(ICON_COLOR_RECORDING)


def icon_processing() -> Image.Image:
    return _create_icon(ICON_COLOR_PROCESSING)
