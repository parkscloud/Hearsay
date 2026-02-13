"""customtkinter appearance configuration."""

from __future__ import annotations

import customtkinter as ctk


def apply_theme() -> None:
    """Set the application-wide theme."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
