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
from hearsay.constants import APP_NAME, LIVE_VIEW_POLL_MS, SOURCE_LABELS
from hearsay.output.formatter import format_timestamp
from hearsay.output.markdown_writer import MarkdownWriter
from hearsay.transcription.engine import TranscriptionEngine
from hearsay.transcription.pipeline import TranscriptionPipeline
from hearsay.ui.about_window import AboutWindow
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
        self._teardown_thread: threading.Thread | None = None
        # Incremented on every start/stop so a slow model load can detect
        # that its session was cancelled before it starts the recorder.
        self._session_gen = 0

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
            on_open_about=self._open_about,
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
        self._session_gen += 1
        session_gen = self._session_gen

        # Fresh queues per session so a previous session's late output can
        # never bleed into this one.
        self._audio_queue = queue.Queue(maxsize=10)
        self._transcript_queue = queue.Queue()
        audio_queue = self._audio_queue
        transcript_queue = self._transcript_queue

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

        engine = self._engine

        def load_and_start() -> None:
            # Wait for any pending teardown to complete first so the old
            # session's recorder has fully released the audio devices.
            if self._teardown_thread is not None:
                self._teardown_thread.join(timeout=30)
                self._teardown_thread = None

            engine.load()

            # The user may have stopped (or restarted) the session while the
            # model was loading — don't start components for a dead session.
            if not self._recording or self._session_gen != session_gen:
                log.info("Session cancelled during model load; not starting recorder")
                engine.unload()
                return

            # Start pipeline
            self._pipeline = TranscriptionPipeline(
                audio_queue=audio_queue,
                transcript_queue=transcript_queue,
                engine=engine,
            )
            self._pipeline.start()

            # Start recorder
            self._recorder = AudioRecorder(
                audio_queue=audio_queue,
                source=source,
                on_fatal=self._on_recorder_fatal,
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
        # Watchdog: catch a recorder that dies without reporting
        self._watch_recorder(self._recorder)

    def _on_recorder_fatal(self, exc: Exception) -> None:
        """Recorder reported an unrecoverable failure (called from its thread)."""
        log.error("Recorder reported fatal error: %s", exc)
        safe_after(self._root, 0, self._handle_recording_failure)

    def _watch_recorder(self, recorder: AudioRecorder | None) -> None:
        """Periodically verify the recorder thread is still alive."""
        if not self._recording or recorder is None or recorder is not self._recorder:
            return
        if not recorder.is_alive():
            log.error("Recorder thread died unexpectedly")
            self._handle_recording_failure()
            return
        safe_after(self._root, 5000, lambda: self._watch_recorder(recorder))

    def _handle_recording_failure(self) -> None:
        """Stop the session loudly when no audio is being captured."""
        if not self._recording:
            return
        log.error("Recording session failed — stopping it")
        if self._tray:
            self._tray.notify(
                "Recording failed — no audio is being captured. "
                "The session has been stopped."
            )
        if self._live_view:
            self._live_view.set_status("Recording FAILED — session stopped")
        self._stop_recording()

    def _stop_recording(self) -> None:
        """Stop the current recording session.

        Updates the tray and UI immediately, then runs the blocking
        teardown (join threads, unload model, finalize file) on a
        background thread so the pystray event loop stays responsive.
        """
        if not self._recording:
            return

        log.info("Stopping recording")
        self._recording = False
        self._session_gen += 1

        # Update tray immediately so the menu is responsive
        if self._tray:
            self._tray.set_recording(False)

        # Update live view status immediately
        safe_after(self._root, 0, lambda: (
            self._live_view.set_status("Saving...") if self._live_view else None
        ))

        # Capture references for the background thread (including the queue —
        # by the time teardown drains it, self._transcript_queue may already
        # belong to the next session)
        recorder = self._recorder
        pipeline = self._pipeline
        engine = self._engine
        writer = self._writer
        start_time = self._recording_start_time
        transcript_queue = self._transcript_queue

        self._recorder = None
        self._pipeline = None
        self._engine = None
        self._writer = None
        self._recording_start_time = None

        self._teardown_thread = threading.Thread(
            target=self._teardown_recording,
            args=(recorder, pipeline, engine, writer, start_time, transcript_queue),
            daemon=True,
            name="RecordingTeardown",
        )
        self._teardown_thread.start()

    def _teardown_recording(
        self,
        recorder: AudioRecorder | None,
        pipeline: TranscriptionPipeline | None,
        engine: TranscriptionEngine | None,
        writer: MarkdownWriter | None,
        start_time: float | None,
        transcript_queue: queue.Queue | None = None,
    ) -> None:
        """Blocking recording teardown — runs on a background thread."""
        # 1. Stop recorder first so it flushes remaining audio to the queue.
        #    Keep waiting until the thread has actually exited — starting the
        #    next session while it still holds the audio devices is what
        #    crashed new recorders in the past.
        if recorder:
            recorder.stop()
            recorder.join(timeout=5)
            waited = 5
            while recorder.is_alive() and waited < 60:
                log.warning(
                    "Recorder thread still running after %ds; continuing to wait",
                    waited,
                )
                recorder.join(timeout=5)
                waited += 5
            if recorder.is_alive():
                log.error(
                    "Recorder thread did not exit after %ds — audio devices "
                    "may still be held (next start will retry opening them)",
                    waited,
                )

        # 2. Stop pipeline -- it will drain any remaining audio chunks before
        #    exiting.  Use a generous timeout so CPU transcription can finish.
        if pipeline:
            pipeline.stop()
            pipeline.join(timeout=60)
            if pipeline.is_alive():
                log.warning("Pipeline thread still running after join timeout")

        # 3. Unload model only after pipeline is done.
        if engine:
            engine.unload()

        # Drain any remaining transcript results that arrived after polling stopped
        if writer and transcript_queue is not None:
            try:
                while True:
                    result = transcript_queue.get_nowait()
                    writer.append(result)
                    if self._live_view:
                        for seg in result.segments:
                            line = self._format_live_line(result, seg)
                            safe_after(self._root, 0,
                                       lambda t=line: (
                                           self._live_view.append_text(t)
                                           if self._live_view else None
                                       ))
            except queue.Empty:
                pass

        # Finalize transcript
        duration = None
        if start_time:
            duration = time.time() - start_time

        if writer:
            path = writer.finalize(total_duration=duration)
            log.info("Transcript saved to %s", path)

            # Post-process: clean up fillers, duplicates, whitespace
            safe_after(self._root, 0, lambda: (
                self._live_view.set_status("Formatting transcript...")
                if self._live_view else None
            ))
            writer.post_process()

            if not writer.body_written:
                log.warning("Session ended with no transcript text")
                if self._tray:
                    self._tray.notify("Recording ended — no speech was captured.")

        # Insert session separator in live view
        end_time = time.strftime("%I:%M %p")
        safe_after(self._root, 0, lambda: (
            self._live_view.append_separator(end_time) if self._live_view else None
        ))

        # Update live view
        safe_after(self._root, 0, lambda: (
            self._live_view.set_status("Idle") if self._live_view else None
        ))

    @staticmethod
    def _format_live_line(result, seg: dict) -> str:
        """Format one segment for the live view, including its source label."""
        ts = format_timestamp(result.window_start + seg["start"])
        label = SOURCE_LABELS.get(seg.get("source", ""))
        if label:
            return f"[{ts}] [{label}] {seg['text']}"
        return f"[{ts}] {seg['text']}"

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
                        self._live_view.append_text(
                            self._format_live_line(result, seg)
                        )
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

    def _open_about(self) -> None:
        """Open the about window."""
        safe_after(
            self._root,
            0,
            lambda: AboutWindow(self._root),
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

        # Run teardown synchronously — responsiveness doesn't matter at exit
        if self._recording:
            self._recording = False
            self._session_gen += 1
            self._teardown_recording(
                self._recorder, self._pipeline, self._engine,
                self._writer, self._recording_start_time,
                self._transcript_queue,
            )
            self._recorder = None
            self._pipeline = None
            self._engine = None
            self._writer = None
            self._recording_start_time = None
        elif self._teardown_thread is not None:
            self._teardown_thread.join(timeout=30)
            self._teardown_thread = None

        if self._tray:
            self._tray.stop()
        safe_after(self._root, 100, self._root.quit)
