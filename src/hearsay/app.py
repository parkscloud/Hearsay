"""Application orchestrator: ties together tray, audio, transcription, and UI."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time

import customtkinter as ctk

from hearsay.audio.recorder import AudioRecorder
from hearsay.config import ConfigManager
from hearsay.constants import APP_NAME, LIVE_VIEW_POLL_MS
from hearsay.output.markdown_writer import MarkdownWriter
from hearsay.transcription.engine import TranscriptionEngine
from hearsay.transcription.pipeline import TranscriptionPipeline
from hearsay.ui.live_view import LiveTranscriptWindow
from hearsay.ui.settings_window import SettingsWindow
from hearsay.ui.theme import apply_theme
from hearsay.ui.tray import SystemTrayIcon
from hearsay.ui.wizard import SetupWizard
from hearsay.utils.threading_utils import safe_after

log = logging.getLogger(__name__)


class HearsayApp:
    """Main application class."""

    def __init__(self) -> None:
        self._config_manager = ConfigManager()
        self._config = self._config_manager.config

        # Queues
        self._audio_queue: queue.Queue = queue.Queue(maxsize=10)
        self._transcript_queue: queue.Queue = queue.Queue()

        # Threads / components
        self._recorder: AudioRecorder | None = None
        self._engine: TranscriptionEngine | None = None
        self._pipeline: TranscriptionPipeline | None = None
        self._writer: MarkdownWriter | None = None
        self._tray: SystemTrayIcon | None = None

        # State
        self._recording = False
        self._recording_start_time: float | None = None

        # UI
        apply_theme()
        self._root = ctk.CTk()
        self._root.withdraw()  # Hidden root window
        self._root.title(APP_NAME)

        self._live_view: LiveTranscriptWindow | None = None

    def run(self) -> None:
        """Start the application."""
        log.info("Starting %s", APP_NAME)

        # Start tray icon in daemon thread
        self._tray = SystemTrayIcon(
            on_start_recording=self._start_recording,
            on_stop_recording=self._stop_recording,
            on_show_live_view=self._toggle_live_view,
            on_open_settings=self._open_settings,
            on_open_output_dir=self._open_output_dir,
            on_quit=self._quit,
        )
        tray_thread = threading.Thread(target=self._tray.run, daemon=True, name="TrayIcon")
        tray_thread.start()

        # Check first-run
        if not self._config.setup_complete:
            self._root.after(500, self._show_wizard)
        else:
            log.info("Config loaded, ready to record")

        # Start tkinter event loop
        self._root.mainloop()

    def _show_wizard(self) -> None:
        """Show the first-run setup wizard."""
        SetupWizard(
            master=self._root,
            config_manager=self._config_manager,
            on_complete=self._on_wizard_complete,
        )

    def _on_wizard_complete(self) -> None:
        """Called when the setup wizard finishes."""
        self._config = self._config_manager.config
        log.info("Wizard complete, app ready")

    def _start_recording(self, source: str) -> None:
        """Start recording from the given source."""
        if self._recording:
            log.warning("Already recording, ignoring start request")
            return

        log.info("Starting recording (source=%s)", source)
        self._recording = True
        self._recording_start_time = time.time()

        # Clear queues
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        while not self._transcript_queue.empty():
            try:
                self._transcript_queue.get_nowait()
            except queue.Empty:
                break

        # Set up markdown writer
        self._writer = MarkdownWriter(self._config.output_dir)

        # Load transcription engine
        self._engine = TranscriptionEngine(
            model_name=self._config.model_name,
            device=self._config.device,
            compute_type=self._config.compute_type,
            language=self._config.language,
            vad_filter=self._config.vad_filter,
        )

        def load_and_start() -> None:
            self._engine.load()

            # Start pipeline
            self._pipeline = TranscriptionPipeline(
                audio_queue=self._audio_queue,
                transcript_queue=self._transcript_queue,
                engine=self._engine,
            )
            self._pipeline.start()

            # Start recorder
            self._recorder = AudioRecorder(
                audio_queue=self._audio_queue,
                source=source,
            )
            self._recorder.start()

            safe_after(self._root, 0, self._on_recording_started)

        threading.Thread(target=load_and_start, daemon=True, name="ModelLoader").start()

        # Update tray
        if self._tray:
            self._tray.set_processing()

        # Update live view
        safe_after(self._root, 0, lambda: self._ensure_live_view().set_status("Loading model..."))

    def _on_recording_started(self) -> None:
        """Called on main thread after model loaded and recording started."""
        if self._tray:
            self._tray.set_recording(True)
        if self._live_view:
            self._live_view.set_status("Recording...")
        # Start polling transcript queue
        self._poll_transcripts()

    def _stop_recording(self) -> None:
        """Stop the current recording session."""
        if not self._recording:
            return

        log.info("Stopping recording")
        self._recording = False

        # 1. Stop recorder first so it flushes remaining audio to the queue.
        if self._recorder:
            self._recorder.stop()
            self._recorder.join(timeout=5)
            self._recorder = None

        # 2. Stop pipeline -- it will drain any remaining audio chunks before
        #    exiting.  Use a generous timeout so CPU transcription can finish.
        if self._pipeline:
            self._pipeline.stop()
            self._pipeline.join(timeout=60)
            if self._pipeline.is_alive():
                log.warning("Pipeline thread still running after join timeout")
            self._pipeline = None

        # 3. Unload model only after pipeline is done.
        if self._engine:
            self._engine.unload()
            self._engine = None

        # Drain any remaining transcript results that arrived after polling stopped
        if self._writer:
            try:
                while True:
                    result = self._transcript_queue.get_nowait()
                    self._writer.append(result)
                    if self._live_view:
                        for seg in result.segments:
                            from hearsay.output.formatter import format_timestamp
                            ts = format_timestamp(
                                result.chunk_index * 30 + seg["start"]
                            )
                            self._live_view.append_text(f"[{ts}] {seg['text']}")
            except queue.Empty:
                pass

        # Finalize transcript
        duration = None
        if self._recording_start_time:
            duration = time.time() - self._recording_start_time
            self._recording_start_time = None

        if self._writer:
            path = self._writer.finalize(total_duration=duration)
            log.info("Transcript saved to %s", path)
            self._writer = None

        # Update tray
        if self._tray:
            self._tray.set_recording(False)

        # Update live view
        safe_after(self._root, 0, lambda: (
            self._live_view.set_status("Idle") if self._live_view else None
        ))

    def _poll_transcripts(self) -> None:
        """Poll the transcript queue and update live view + markdown writer."""
        if not self._recording:
            return

        try:
            while True:
                result = self._transcript_queue.get_nowait()
                # Write to markdown
                if self._writer:
                    self._writer.append(result)
                # Update live view
                if self._live_view:
                    for seg in result.segments:
                        from hearsay.output.formatter import format_timestamp
                        ts = format_timestamp(
                            result.chunk_index * 30 + seg["start"]
                        )
                        self._live_view.append_text(f"[{ts}] {seg['text']}")
        except queue.Empty:
            pass

        # Schedule next poll
        if self._recording:
            safe_after(self._root, LIVE_VIEW_POLL_MS, self._poll_transcripts)

    def _ensure_live_view(self) -> LiveTranscriptWindow:
        """Create live view if needed, return it."""
        if self._live_view is None:
            self._live_view = LiveTranscriptWindow(self._root)
        return self._live_view

    def _toggle_live_view(self) -> None:
        """Toggle the live transcript window."""
        safe_after(self._root, 0, lambda: self._ensure_live_view().toggle())

    def _open_settings(self) -> None:
        """Open the settings window."""
        safe_after(
            self._root,
            0,
            lambda: SettingsWindow(self._root, self._config_manager),
        )

    def _open_output_dir(self) -> None:
        """Open the output directory in file explorer."""
        path = self._config.output_dir
        try:
            os.startfile(path)
        except Exception:
            log.warning("Could not open directory: %s", path, exc_info=True)

    def _quit(self) -> None:
        """Clean shutdown."""
        log.info("Shutting down %s", APP_NAME)
        self._stop_recording()
        if self._tray:
            self._tray.stop()
        safe_after(self._root, 100, self._root.quit)
