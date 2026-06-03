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
            text="Live text (gray) updates as you speak; it is replaced by the final, more accurate text after a brief pause.",
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

        # The tentative (in-progress) line is rendered in gray and replaced in
        # place each time RealtimeSTT revises it, then committed as a final line.
        self._textbox.tag_config("tentative", foreground="#888888")
        self._tent_start_index: str | None = None

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
        """Append a finished line to the transcript view."""
        self._textbox.configure(state="normal")
        self._textbox.insert("end", text + "\n")
        self._textbox.configure(state="disabled")
        if self._autoscroll.get():
            self._textbox.see("end")

    def update_tentative(self, text: str) -> None:
        """Show or revise the in-progress (gray) line at the bottom of the view."""
        tb = self._textbox
        tb.configure(state="normal")
        if self._tent_start_index is None:
            self._tent_start_index = tb.index("end-1c")
        else:
            tb.delete(self._tent_start_index, "end-1c")
        tb.insert(self._tent_start_index, text)
        tb.tag_add("tentative", self._tent_start_index, "end-1c")
        tb.configure(state="disabled")
        if self._autoscroll.get():
            tb.see("end")

    def commit_final(self, line: str) -> None:
        """Replace the tentative line (if any) with a committed final line."""
        tb = self._textbox
        tb.configure(state="normal")
        if self._tent_start_index is not None:
            tb.delete(self._tent_start_index, "end-1c")
            self._tent_start_index = None
        tb.insert("end-1c", line + "\n")
        tb.configure(state="disabled")
        if self._autoscroll.get():
            tb.see("end")

    def drop_tentative(self) -> None:
        """Discard the in-progress line without committing it."""
        if self._tent_start_index is None:
            return
        tb = self._textbox
        tb.configure(state="normal")
        tb.delete(self._tent_start_index, "end-1c")
        self._tent_start_index = None
        tb.configure(state="disabled")

    def append_separator(self, timestamp: str) -> None:
        """Insert a visual divider marking the end of a recording session."""
        self.drop_tentative()
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
        self._tent_start_index = None
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
