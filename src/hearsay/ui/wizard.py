"""First-run setup wizard with 5 screens."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from hearsay.audio.devices import (
    get_default_loopback,
    get_default_microphone,
    list_loopback_devices,
    list_microphone_devices,
)
from hearsay.config import AppConfig, ConfigManager
from hearsay.constants import (
    APP_NAME,
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MIC,
    AUDIO_SOURCE_SYSTEM,
    MODEL_TABLE,
)
from hearsay.transcription.gpu_detect import GPUInfo, detect_gpu
from hearsay.transcription.model_manager import download_model
from hearsay.utils.paths import get_default_output_dir

log = logging.getLogger(__name__)


class SetupWizard(ctk.CTkToplevel):
    """First-run setup wizard.

    Screens:
        1. Welcome + GPU detection
        2. Audio source selection
        3. Output directory
        4. Model download
        5. Complete
    """

    def __init__(
        self,
        master: ctk.CTk,
        config_manager: ConfigManager,
        on_complete: callable,
    ) -> None:
        super().__init__(master)
        self.title(f"{APP_NAME} Setup")
        self.geometry("600x480")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._config_manager = config_manager
        self._config = config_manager.config
        self._on_complete = on_complete
        self._gpu_info: GPUInfo | None = None
        self._current_screen = 0

        # Container for screens
        self._container = ctk.CTkFrame(self)
        self._container.pack(fill="both", expand=True, padx=20, pady=20)

        # Navigation buttons
        self._nav_frame = ctk.CTkFrame(self)
        self._nav_frame.pack(fill="x", padx=20, pady=(0, 20))

        self._back_btn = ctk.CTkButton(
            self._nav_frame, text="Back", width=100, command=self._prev_screen
        )
        self._back_btn.pack(side="left")

        self._next_btn = ctk.CTkButton(
            self._nav_frame, text="Next", width=100, command=self._next_screen
        )
        self._next_btn.pack(side="right")

        self._show_screen(0)
        self.grab_set()

    def _clear_container(self) -> None:
        for widget in self._container.winfo_children():
            widget.destroy()

    def _show_screen(self, index: int) -> None:
        self._current_screen = index
        self._clear_container()
        self._back_btn.configure(state="normal" if index > 0 else "disabled")

        screens = [
            self._screen_welcome,
            self._screen_audio,
            self._screen_output,
            self._screen_model_download,
            self._screen_complete,
        ]
        screens[index]()

    def _next_screen(self) -> None:
        if self._current_screen < 4:
            self._show_screen(self._current_screen + 1)

    def _prev_screen(self) -> None:
        if self._current_screen > 0:
            self._show_screen(self._current_screen - 1)

    def _on_close(self) -> None:
        """If wizard is closed early, save partial config."""
        self.grab_release()
        self.destroy()

    # ── Screen 1: Welcome + GPU Detection ──

    def _screen_welcome(self) -> None:
        self._next_btn.configure(text="Next", state="normal")

        ctk.CTkLabel(
            self._container,
            text=f"Welcome to {APP_NAME}!",
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            self._container,
            text="Record system audio and transcribe it locally using AI.",
            font=("Segoe UI", 13),
            text_color="gray",
        ).pack(pady=(0, 20))

        # GPU detection
        self._gpu_label = ctk.CTkLabel(
            self._container,
            text="Detecting hardware...",
            font=("Segoe UI", 12),
        )
        self._gpu_label.pack(pady=10)

        self._rec_label = ctk.CTkLabel(
            self._container,
            text="",
            font=("Segoe UI", 12),
            text_color="#4da6ff",
        )
        self._rec_label.pack(pady=5)

        # Run detection in background
        threading.Thread(target=self._detect_gpu_bg, daemon=True).start()

    def _detect_gpu_bg(self) -> None:
        self._gpu_info = detect_gpu()
        info = self._gpu_info
        if info.cuda_available:
            hw_text = f"GPU detected: {info.gpu_name} ({info.vram_gb} GB VRAM)"
        else:
            hw_text = "No NVIDIA GPU detected. Will use CPU transcription."
        rec_text = f"Recommended: {info.recommended_model} ({info.recommended_compute})"

        # Apply to config
        self._config.model_name = info.recommended_model
        self._config.compute_type = info.recommended_compute
        self._config.device = info.recommended_device

        self.after(0, lambda: self._gpu_label.configure(text=hw_text))
        self.after(0, lambda: self._rec_label.configure(text=rec_text))

    # ── Screen 2: Audio Source ──

    def _screen_audio(self) -> None:
        self._next_btn.configure(text="Next", state="normal")

        ctk.CTkLabel(
            self._container,
            text="Audio Source",
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            self._container,
            text="Choose what to record (you can change this per session).",
            font=("Segoe UI", 12),
            text_color="gray",
        ).pack(pady=(0, 15))

        self._source_var = ctk.StringVar(value=self._config.audio_source)

        options = [
            (AUDIO_SOURCE_SYSTEM, "System Audio", "Record what your speakers play (YouTube, Teams, etc.)"),
            (AUDIO_SOURCE_MIC, "Microphone", "Record from your microphone"),
            (AUDIO_SOURCE_BOTH, "Both", "Mix system audio and microphone together"),
        ]
        for value, label, desc in options:
            frame = ctk.CTkFrame(self._container)
            frame.pack(fill="x", pady=3)
            ctk.CTkRadioButton(
                frame,
                text=label,
                variable=self._source_var,
                value=value,
                font=("Segoe UI", 13),
                command=lambda v=value: setattr(self._config, "audio_source", v),
            ).pack(anchor="w", padx=10, pady=(5, 0))
            ctk.CTkLabel(
                frame,
                text=desc,
                font=("Segoe UI", 11),
                text_color="gray",
            ).pack(anchor="w", padx=35, pady=(0, 5))

    # ── Screen 3: Output Directory ──

    def _screen_output(self) -> None:
        self._next_btn.configure(text="Next", state="normal")

        ctk.CTkLabel(
            self._container,
            text="Output Directory",
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            self._container,
            text="Where should transcripts be saved?",
            font=("Segoe UI", 12),
            text_color="gray",
        ).pack(pady=(0, 15))

        dir_frame = ctk.CTkFrame(self._container)
        dir_frame.pack(fill="x", pady=10)

        self._dir_var = ctk.StringVar(value=self._config.output_dir)
        self._dir_entry = ctk.CTkEntry(
            dir_frame,
            textvariable=self._dir_var,
            width=400,
            font=("Consolas", 12),
        )
        self._dir_entry.pack(side="left", padx=(10, 5), pady=10)

        ctk.CTkButton(
            dir_frame,
            text="Browse",
            width=80,
            command=self._browse_output_dir,
        ).pack(side="left", padx=5, pady=10)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(
            initialdir=self._config.output_dir,
            title="Select Output Directory",
        )
        if path:
            self._dir_var.set(path)
            self._config.output_dir = path

    # ── Screen 4: Model Download ──

    def _screen_model_download(self) -> None:
        self._next_btn.configure(text="Next", state="disabled")

        ctk.CTkLabel(
            self._container,
            text="Download Model",
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(10, 5))

        model = self._config.model_name
        info = MODEL_TABLE.get(model, ("?", 0, False))

        ctk.CTkLabel(
            self._container,
            text=f"Model: {model} ({info[0]} parameters)",
            font=("Segoe UI", 13),
        ).pack(pady=(0, 5))

        self._dl_status = ctk.CTkLabel(
            self._container,
            text="Starting download...",
            font=("Segoe UI", 12),
            text_color="gray",
        )
        self._dl_status.pack(pady=10)

        self._dl_progress = ctk.CTkProgressBar(self._container, width=400)
        self._dl_progress.pack(pady=10)
        self._dl_progress.set(0)
        self._dl_progress.configure(mode="indeterminate")
        self._dl_progress.start()

        threading.Thread(target=self._download_model_bg, daemon=True).start()

    def _download_model_bg(self) -> None:
        def update_status(text: str) -> None:
            self.after(0, lambda: self._dl_status.configure(text=text))

        try:
            download_model(self._config.model_name, progress_callback=update_status)
            self.after(0, self._download_complete)
        except Exception as e:
            log.error("Model download failed", exc_info=True)
            self.after(0, lambda: self._dl_status.configure(
                text=f"Download failed: {e}", text_color="red"
            ))
            self.after(0, lambda: self._next_btn.configure(state="normal"))

    def _download_complete(self) -> None:
        self._dl_progress.stop()
        self._dl_progress.set(1)
        self._dl_progress.configure(mode="determinate")
        self._dl_status.configure(text="Model downloaded successfully!", text_color="#4da6ff")
        self._next_btn.configure(state="normal")

    # ── Screen 5: Complete ──

    def _screen_complete(self) -> None:
        self._next_btn.configure(text="Finish", state="normal", command=self._finish)
        self._back_btn.configure(state="disabled")

        ctk.CTkLabel(
            self._container,
            text="Setup Complete!",
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            self._container,
            text=f"{APP_NAME} is ready to use.",
            font=("Segoe UI", 14),
        ).pack(pady=5)

        ctk.CTkLabel(
            self._container,
            text="Right-click the tray icon to start recording.",
            font=("Segoe UI", 12),
            text_color="gray",
        ).pack(pady=5)

        summary = (
            f"Audio source: {self._config.audio_source}\n"
            f"Model: {self._config.model_name} ({self._config.compute_type})\n"
            f"Device: {self._config.device}\n"
            f"Output: {self._config.output_dir}"
        )
        ctk.CTkLabel(
            self._container,
            text=summary,
            font=("Consolas", 11),
            justify="left",
        ).pack(pady=15)

    def _finish(self) -> None:
        # Save config
        self._config.output_dir = getattr(self, "_dir_var", ctk.StringVar(value=self._config.output_dir)).get()
        self._config.setup_complete = True
        self._config_manager.save()
        log.info("Setup wizard completed")
        self.grab_release()
        self.destroy()
        self._on_complete()
