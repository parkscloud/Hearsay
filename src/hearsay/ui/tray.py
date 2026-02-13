"""System tray icon using pystray in a daemon thread."""

from __future__ import annotations

import logging
from typing import Callable

import pystray
from pystray import MenuItem as Item

from hearsay.constants import (
    APP_NAME,
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MIC,
    AUDIO_SOURCE_SYSTEM,
)
from hearsay.ui.icons import icon_idle, icon_processing, icon_recording

log = logging.getLogger(__name__)


class SystemTrayIcon:
    """Manages the system tray icon and its context menu.

    Args:
        on_start_recording: Callback(source: str) to start recording.
        on_stop_recording: Callback() to stop recording.
        on_show_live_view: Callback() to toggle the live transcript window.
        on_open_settings: Callback() to open the settings window.
        on_open_output_dir: Callback() to open the output directory.
        on_quit: Callback() to quit the application.
    """

    def __init__(
        self,
        on_start_recording: Callable[[str], None],
        on_stop_recording: Callable[[], None],
        on_show_live_view: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_open_output_dir: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_start_recording = on_start_recording
        self._on_stop_recording = on_stop_recording
        self._on_show_live_view = on_show_live_view
        self._on_open_settings = on_open_settings
        self._on_open_output_dir = on_open_output_dir
        self._on_quit = on_quit
        self._recording = False
        self._icon: pystray.Icon | None = None

    def _build_menu(self) -> pystray.Menu:
        if self._recording:
            return pystray.Menu(
                Item("Stop Recording", lambda: self._on_stop_recording()),
                pystray.Menu.SEPARATOR,
                Item("Live Transcript", lambda: self._on_show_live_view()),
                Item("Open Transcripts Folder", lambda: self._on_open_output_dir()),
                pystray.Menu.SEPARATOR,
                Item("Settings", lambda: self._on_open_settings()),
                Item("Quit", lambda: self._on_quit()),
            )
        return pystray.Menu(
            Item(
                "Start Recording",
                pystray.Menu(
                    Item("System Audio", lambda: self._start(AUDIO_SOURCE_SYSTEM)),
                    Item("Microphone", lambda: self._start(AUDIO_SOURCE_MIC)),
                    Item("Both", lambda: self._start(AUDIO_SOURCE_BOTH)),
                ),
            ),
            pystray.Menu.SEPARATOR,
            Item("Live Transcript", lambda: self._on_show_live_view()),
            Item("Open Transcripts Folder", lambda: self._on_open_output_dir()),
            pystray.Menu.SEPARATOR,
            Item("Settings", lambda: self._on_open_settings()),
            Item("Quit", lambda: self._on_quit()),
        )

    def _start(self, source: str) -> None:
        self._on_start_recording(source)

    def set_recording(self, recording: bool) -> None:
        """Update icon state to reflect recording status."""
        self._recording = recording
        if self._icon:
            self._icon.icon = icon_recording() if recording else icon_idle()
            self._icon.menu = self._build_menu()
            self._icon.update_menu()

    def set_processing(self) -> None:
        """Show processing state (blue icon)."""
        if self._icon:
            self._icon.icon = icon_processing()

    def run(self) -> None:
        """Start the tray icon (blocking -- run in a daemon thread)."""
        self._icon = pystray.Icon(
            APP_NAME,
            icon=icon_idle(),
            title=APP_NAME,
            menu=self._build_menu(),
        )
        log.info("System tray icon started")
        self._icon.run()

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._icon:
            self._icon.stop()
            log.info("System tray icon stopped")
