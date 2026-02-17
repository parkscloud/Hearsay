"""Toggleable live transcript window."""

from __future__ import annotations

import logging
import tkinter as tk

import customtkinter as ctk

from hearsay.constants import APP_NAME

log = logging.getLogger(__name__)


class LiveTranscriptWindow(ctk.CTkToplevel):
    """A floating window that displays transcript text as it arrives.

    The window hides (withdraw) on close rather than destroying,
    so it can be toggled back from the tray menu.
    """

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        self.title(f"{APP_NAME} - Live Transcript")
        self.geometry("700x500")
        self.minsize(400, 300)

        # Hide on close rather than destroy
        self.protocol("WM_DELETE_WINDOW", self.hide)

        # Delay disclaimer
        ctk.CTkLabel(
            self,
            text="Transcript text appears with a delay of approximately 30\u201360 seconds depending on your hardware.",
            font=("Segoe UI", 10, "italic"),
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 0))

        # Transcript text area
        self._textbox = ctk.CTkTextbox(
            self,
            wrap="word",
            font=("Consolas", 13),
            state="disabled",
        )
        self._textbox.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        # Bottom bar with status and controls
        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self._status_label = ctk.CTkLabel(
            bottom,
            text="Idle",
            font=("Segoe UI", 11),
            text_color="gray",
        )
        self._status_label.pack(side="left", padx=5)

        self._clear_btn = ctk.CTkButton(
            bottom,
            text="Clear",
            width=70,
            command=self.clear,
        )
        self._clear_btn.pack(side="right", padx=5)

        self._autoscroll = tk.BooleanVar(value=True)
        self._scroll_check = ctk.CTkCheckBox(
            bottom,
            text="Auto-scroll",
            variable=self._autoscroll,
            width=100,
        )
        self._scroll_check.pack(side="right", padx=5)

        # Start hidden
        self.withdraw()

    def show(self) -> None:
        """Show the window."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self) -> None:
        """Hide the window without destroying it."""
        self.withdraw()

    def toggle(self) -> None:
        """Toggle visibility."""
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()

    def append_text(self, text: str) -> None:
        """Append text to the transcript view."""
        self._textbox.configure(state="normal")
        self._textbox.insert("end", text + "\n")
        self._textbox.configure(state="disabled")
        if self._autoscroll.get():
            self._textbox.see("end")

    def append_separator(self, timestamp: str) -> None:
        """Insert a visual divider marking the end of a recording session."""
        self._textbox.configure(state="normal")
        self._textbox.insert("end", f"\n--- Recording ended at {timestamp} ---\n\n")
        self._textbox.configure(state="disabled")
        if self._autoscroll.get():
            self._textbox.see("end")

    def set_status(self, text: str) -> None:
        """Update the status label."""
        self._status_label.configure(text=text)

    def clear(self) -> None:
        """Clear all transcript text."""
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
