"""Application orchestrator: ties together tray, audio, transcription, and UI."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time

import webbrowser

import customtkinter as ctk

from hearsay.audio.recorder import AudioRecorder
from hearsay.config import ConfigManager
from hearsay.constants import APP_NAME, DEFAULT_CPU_COMPUTE
from hearsay.output.markdown_writer import MarkdownWriter
from hearsay.transcription.realtime_engine import CudaUnavailableError, RealtimeEngine
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

        # Threads / components
        self._recorder: AudioRecorder | None = None
        self._engine: RealtimeEngine | None = None
        self._writer: MarkdownWriter | None = None
        self._tray: SystemTrayIcon | None = None

        # State
        self._recording = False
        self._recording_start_time: float | None = None
        self._utterance_start_elapsed: float | None = None
        self._teardown_thread: threading.Thread | None = None
        self._hotkey_combo: str | None = None

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
            self._register_hotkey()

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
        self._register_hotkey()

    def _start_recording(self, source: str) -> None:
        """Start recording from the given source."""
        if self._recording:
            log.warning("Already recording, ignoring start request")
            return

        log.info("Starting recording (source=%s)", source)
        self._recording = True
        self._recording_start_time = time.time()
        self._utterance_start_elapsed = None

        # Set up markdown writer
        self._writer = MarkdownWriter(
            self._config.output_dir, language=self._config.language
        )

        # Dual-layer realtime engine (tentative + final)
        self._engine = RealtimeEngine(
            model_name=self._config.model_name,
            realtime_model_name=self._config.realtime_model_name,
            device=self._config.device,
            compute_type=self._config.compute_type,
            language=self._config.language,
            on_tentative=self._on_tentative,
            on_final=self._on_final,
            on_utterance_start=self._on_utterance_start,
            post_speech_silence_duration=self._config.post_speech_silence_duration,
        )

        def load_and_start() -> None:
            # Wait for any pending teardown to complete first
            if self._teardown_thread is not None:
                self._teardown_thread.join(timeout=30)
                self._teardown_thread = None

            # Download HF model on-demand (deferred from settings save)
            from hearsay.transcription.model_manager import (
                download_model, is_hf_custom_model, is_model_downloaded,
            )
            if (is_hf_custom_model(self._engine.model_name)
                    and not is_model_downloaded(self._engine.model_name)):
                safe_after(self._root, 0, lambda: self._ensure_live_view().set_status("Downloading model..."))
                try:
                    def _dl_progress(msg: str) -> None:
                        safe_after(self._root, 0,
                                   lambda m=msg: self._ensure_live_view().set_status(f"Downloading: {m}"))
                    download_model(self._engine.model_name, progress_callback=_dl_progress)
                except Exception as exc:
                    log.error("Model download failed at recording start", exc_info=True)
                    safe_after(self._root, 0, lambda e=str(exc): self._on_model_download_failed(e))
                    return

            safe_after(self._root, 0, lambda: self._ensure_live_view().set_status("Loading model..."))
            try:
                self._engine.load()
            except CudaUnavailableError:
                safe_after(self._root, 0, lambda: self._handle_cuda_error(source))
                return

            # Start recorder in streaming mode — frames feed straight into the engine
            self._recorder = AudioRecorder(
                queue.Queue(),
                source=source,
                on_frame=self._engine.feed,
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
        if self._config.beep_on_start:
            threading.Thread(target=self._play_beep, args=("start",), daemon=True).start()

    # ── Transcription callbacks (from the engine threads) ───────────────────────

    def _on_utterance_start(self) -> None:
        """RealtimeSTT detected speech onset — stamp the utterance's start time."""
        if self._recording_start_time is not None:
            self._utterance_start_elapsed = time.time() - self._recording_start_time

    def _on_tentative(self, text: str) -> None:
        """Revised in-progress text from the fast realtime model (gray layer)."""
        safe_after(self._root, 0, lambda t=text: (
            self._live_view.update_tentative(t) if self._live_view else None
        ))

    def _on_final(self, text: str) -> None:
        """Finalized, accurate text for a completed utterance (committed layer)."""
        elapsed = self._utterance_start_elapsed
        if elapsed is None and self._recording_start_time is not None:
            elapsed = time.time() - self._recording_start_time
        elapsed = elapsed or 0.0
        self._utterance_start_elapsed = None

        if self._writer:
            self._writer.append_utterance(elapsed, text)

        from hearsay.output.formatter import format_timestamp
        line = f"[{format_timestamp(elapsed)}] {text}"
        safe_after(self._root, 0, lambda l=line: (
            self._live_view.commit_final(l) if self._live_view else None
        ))

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

        if self._config.beep_on_stop:
            threading.Thread(target=self._play_beep, args=("stop",), daemon=True).start()

        # Update tray immediately so the menu is responsive
        if self._tray:
            self._tray.set_recording(False)

        # Update live view status immediately
        safe_after(self._root, 0, lambda: (
            self._live_view.set_status("Saving...") if self._live_view else None
        ))

        # Capture references for the background thread
        recorder = self._recorder
        engine = self._engine
        writer = self._writer
        start_time = self._recording_start_time

        self._recorder = None
        self._engine = None
        self._writer = None
        self._recording_start_time = None

        self._teardown_thread = threading.Thread(
            target=self._teardown_recording,
            args=(recorder, engine, writer, start_time),
            daemon=True,
            name="RecordingTeardown",
        )
        self._teardown_thread.start()

    def _teardown_recording(
        self,
        recorder: AudioRecorder | None,
        engine: RealtimeEngine | None,
        writer: MarkdownWriter | None,
        start_time: float | None,
    ) -> None:
        """Blocking recording teardown — runs on a background thread."""
        # 1. Stop recorder first so it stops feeding audio into the engine.
        if recorder:
            recorder.stop()
            recorder.join(timeout=5)

        # 2. Shut down the engine (stops both models and the child process).
        if engine:
            engine.shutdown()

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

            if self._config.beep_on_save:
                self._play_beep("save")

            if self._config.copy_to_clipboard:
                text = self._extract_clipboard_text(writer)
                if text:
                    safe_after(self._root, 0, lambda t=text: self._copy_to_clipboard(t))

        # Insert session separator in live view
        end_time = time.strftime("%I:%M %p")
        safe_after(self._root, 0, lambda: (
            self._live_view.append_separator(end_time) if self._live_view else None
        ))

        # Update live view
        safe_after(self._root, 0, lambda: (
            self._live_view.set_status("Idle") if self._live_view else None
        ))

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
            lambda: SettingsWindow(
                self._root,
                self._config_manager,
                on_save=self._on_settings_saved,
                is_recording=lambda: self._recording,
            ),
        )

    def _on_settings_saved(self) -> None:
        self._config = self._config_manager.config
        self._register_hotkey()

    def _open_about(self) -> None:
        """Open the about window."""
        safe_after(
            self._root,
            0,
            lambda: AboutWindow(self._root),
        )

    def _on_model_download_failed(self, error: str) -> None:
        """Called on main thread when model download fails at recording start."""
        self._recording = False
        self._engine = None
        if self._tray:
            self._tray.set_recording(False)
        if self._live_view:
            self._live_view.set_status("Download failed")
        from tkinter import messagebox
        messagebox.showerror(
            "Model Download Failed",
            "Failed to download the selected model. Check your internet connection "
            "or select a different model in Settings.\n\n" + error[:200],
            parent=self._root,
        )

    def _handle_cuda_error(self, source: str) -> None:
        """Called on main thread when CUDA runtime DLLs are missing."""
        self._recording = False
        self._engine = None
        if self._tray:
            self._tray.set_recording(False)
        if self._live_view:
            self._live_view.set_status("Idle")
        self._show_cuda_error_dialog(source)

    def _show_cuda_error_dialog(self, source: str) -> None:
        """Show a dialog offering CPU fallback or CUDA Toolkit install link."""
        dialog = ctk.CTkToplevel(self._root)
        dialog.title("GPU Unavailable")
        dialog.resizable(False, False)
        dialog.grab_set()

        # Center on screen
        dialog.update_idletasks()
        w, h = 420, 220
        x = (dialog.winfo_screenwidth() - w) // 2
        y = (dialog.winfo_screenheight() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="CUDA runtime library not found.",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            dialog,
            text=(
                "GPU is selected but CUDA Toolkit 12.x is not installed,\n"
                "so inference cannot run on GPU.\n\n"
                "Switch to CPU or install CUDA Toolkit to continue."
            ),
            justify="center",
        ).pack(pady=(0, 16))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()

        def switch_to_cpu() -> None:
            dialog.destroy()
            self._config.device = "cpu"
            self._config.compute_type = DEFAULT_CPU_COMPUTE
            self._config_manager.save()
            log.info("Switched to CPU per user request after CUDA error")
            self._start_recording(source)

        def open_cuda_download() -> None:
            dialog.destroy()
            webbrowser.open("https://developer.nvidia.com/cuda-downloads")

        ctk.CTkButton(
            btn_frame, text="Switch to CPU", width=160, command=switch_to_cpu,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="Install CUDA Toolkit", width=160,
            fg_color="transparent", border_width=1,
            command=open_cuda_download,
        ).pack(side="left", padx=8)

    # ── Hotkey ────────────────────────────────────────────────────────────────

    def _register_hotkey(self) -> None:
        try:
            import keyboard as kb
            self._unregister_hotkey()
            combo = self._config.hotkey
            if combo:
                kb.add_hotkey(combo, self._toggle_recording_hotkey)
                self._hotkey_combo = combo
                log.info("Hotkey registered: %s", combo)
        except Exception:
            log.warning("Failed to register hotkey", exc_info=True)

    def _unregister_hotkey(self) -> None:
        try:
            import keyboard as kb
            if self._hotkey_combo:
                kb.remove_hotkey(self._hotkey_combo)
                self._hotkey_combo = None
        except Exception:
            pass

    def _toggle_recording_hotkey(self) -> None:
        """Called from the keyboard library thread — must dispatch to main thread."""
        if self._recording:
            safe_after(self._root, 0, self._stop_recording)
        else:
            safe_after(self._root, 0, lambda: self._start_recording(self._config.audio_source))

    # ── Beep ──────────────────────────────────────────────────────────────────

    def _play_beep(self, event: str) -> None:
        try:
            import winsound
            if event == "start":
                winsound.Beep(880, 120)
            elif event == "stop":
                winsound.Beep(520, 180)
            elif event == "save":
                winsound.Beep(660, 80)
                winsound.Beep(880, 160)
        except Exception:
            pass

    # ── Clipboard ─────────────────────────────────────────────────────────────

    def _extract_clipboard_text(self, writer: MarkdownWriter) -> str:
        try:
            content = writer.file_path.read_text(encoding="utf-8")
            header_end = content.index("\n\n") + 2
            footer_idx = content.rfind("\n---\n")
            body = content[header_end:footer_idx] if footer_idx != -1 else content[header_end:]
            return body.strip()
        except Exception:
            log.warning("Failed to extract clipboard text", exc_info=True)
            return ""

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            self._root.clipboard_clear()
            self._root.clipboard_append(text)
            log.info("Transcript copied to clipboard (%d chars)", len(text))
        except Exception:
            log.warning("Failed to copy to clipboard", exc_info=True)

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
            self._teardown_recording(
                self._recorder, self._engine,
                self._writer, self._recording_start_time,
            )
            self._recorder = None
            self._engine = None
            self._writer = None
            self._recording_start_time = None
        elif self._teardown_thread is not None:
            self._teardown_thread.join(timeout=30)
            self._teardown_thread = None

        self._unregister_hotkey()
        if self._tray:
            self._tray.stop()
        safe_after(self._root, 100, self._root.quit)
