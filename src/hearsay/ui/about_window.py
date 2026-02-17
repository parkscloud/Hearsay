"""About window showing project info, acknowledgements, and license."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from hearsay.constants import APP_NAME, APP_VERSION

GITHUB_URL = "https://github.com/parkscloud/Hearsay"

ACKNOWLEDGEMENTS = [
    "faster-whisper",
    "PyAudioWPatch",
    "sounddevice",
    "customtkinter",
    "pystray + Pillow",
]


class AboutWindow(ctk.CTkToplevel):
    """Modal About dialog."""

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        self.title(f"About {APP_NAME}")
        self.geometry("450x400")
        self.resizable(False, False)

        # App name + version
        ctk.CTkLabel(
            self,
            text=APP_NAME,
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(20, 2))

        ctk.CTkLabel(
            self,
            text=f"Version {APP_VERSION}",
            font=("Segoe UI", 13),
            text_color="gray",
        ).pack(pady=(0, 10))

        # Author
        ctk.CTkLabel(
            self,
            text="Author: Robert Parks",
            font=("Segoe UI", 12),
        ).pack(pady=(0, 5))

        # GitHub link
        link = ctk.CTkLabel(
            self,
            text=GITHUB_URL,
            font=("Segoe UI", 12, "underline"),
            text_color="#1f6aa5",
            cursor="hand2",
        )
        link.pack(pady=(0, 15))
        link.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

        # Acknowledgements
        ctk.CTkLabel(
            self,
            text="Acknowledgements",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=30, pady=(0, 5))

        for name in ACKNOWLEDGEMENTS:
            ctk.CTkLabel(
                self,
                text=f"  \u2022  {name}",
                font=("Segoe UI", 12),
                anchor="w",
            ).pack(anchor="w", padx=35)

        # License
        ctk.CTkLabel(
            self,
            text="License: MIT",
            font=("Segoe UI", 12),
            text_color="gray",
        ).pack(pady=(15, 0))

        # Close button
        ctk.CTkButton(
            self,
            text="Close",
            width=100,
            command=self._close,
        ).pack(pady=(15, 20))

        self.grab_set()

    def _close(self) -> None:
        self.grab_release()
        self.destroy()
