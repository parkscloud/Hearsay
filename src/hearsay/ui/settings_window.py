"""Post-setup settings editor window."""

from __future__ import annotations

import logging
import threading
from tkinter import filedialog

import customtkinter as ctk

from hearsay.config import ConfigManager
from hearsay.constants import (
    APP_NAME,
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MIC,
    AUDIO_SOURCE_SYSTEM,
    MODEL_TABLE,
)
from hearsay.transcription.model_manager import (
    download_model,
    is_hf_custom_model,
    is_model_downloaded,
)

log = logging.getLogger(__name__)


class SettingsWindow(ctk.CTkToplevel):
    """Settings editor window."""

    def __init__(self, master: ctk.CTk, config_manager: ConfigManager) -> None:
        super().__init__(master)
        self.title(f"{APP_NAME} Settings")
        self.geometry("550x520")
        self.resizable(False, False)

        self._config_manager = config_manager
        self._config = config_manager.config
        self._dl_frame: ctk.CTkFrame | None = None

        self._build_ui()
        self.grab_set()

    def _build_ui(self) -> None:
        # Title
        ctk.CTkLabel(
            self,
            text="Settings",
            font=("Segoe UI", 20, "bold"),
        ).pack(pady=(15, 10))

        # Scrollable content
        scroll = ctk.CTkScrollableFrame(self, width=490, height=360)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # ── Audio Source ──
        ctk.CTkLabel(scroll, text="Default Audio Source", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(10, 5)
        )
        self._source_var = ctk.StringVar(value=self._config.audio_source)
        for value, label in [
            (AUDIO_SOURCE_SYSTEM, "System Audio"),
            (AUDIO_SOURCE_MIC, "Microphone"),
            (AUDIO_SOURCE_BOTH, "Both"),
        ]:
            ctk.CTkRadioButton(
                scroll, text=label, variable=self._source_var, value=value
            ).pack(anchor="w", padx=15, pady=2)

        # ── Model ──
        ctk.CTkLabel(scroll, text="Whisper Model", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        self._model_var = ctk.StringVar(value=self._config.model_name)
        self._model_menu = ctk.CTkOptionMenu(
            scroll,
            variable=self._model_var,
            values=list(MODEL_TABLE.keys()),
            width=200,
            command=self._on_model_changed,
        )
        self._model_menu.pack(anchor="w", padx=15)

        self._model_hint = ctk.CTkLabel(
            scroll, text="", font=("Segoe UI", 10), text_color="gray"
        )
        self._model_hint.pack(anchor="w", padx=15)
        self._update_model_hint(self._config.model_name)

        # ── Compute Type ──
        ctk.CTkLabel(scroll, text="Compute Type", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        self._compute_var = ctk.StringVar(value=self._config.compute_type)
        self._compute_menu = ctk.CTkOptionMenu(
            scroll,
            variable=self._compute_var,
            values=["float16", "int8", "float32"],
            width=200,
        )
        self._compute_menu.pack(anchor="w", padx=15)

        # ── Device ──
        ctk.CTkLabel(scroll, text="Device", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        self._device_var = ctk.StringVar(value=self._config.device)
        ctk.CTkRadioButton(
            scroll, text="CPU", variable=self._device_var, value="cpu"
        ).pack(anchor="w", padx=15, pady=2)
        ctk.CTkRadioButton(
            scroll, text="CUDA (GPU)", variable=self._device_var, value="cuda"
        ).pack(anchor="w", padx=15, pady=2)

        # ── Language ──
        ctk.CTkLabel(scroll, text="Language", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        self._lang_var = ctk.StringVar(value=self._config.language)
        self._lang_entry = ctk.CTkEntry(scroll, textvariable=self._lang_var, width=100)
        self._lang_entry.pack(anchor="w", padx=15)
        ctk.CTkLabel(
            scroll, text="ISO 639-1 code (e.g., en, ko, fr) or empty for auto-detect",
            font=("Segoe UI", 10), text_color="gray"
        ).pack(anchor="w", padx=15)

        # ── VAD ──
        self._vad_var = ctk.BooleanVar(value=self._config.vad_filter)
        ctk.CTkCheckBox(
            scroll, text="Enable VAD filter (recommended)", variable=self._vad_var
        ).pack(anchor="w", padx=15, pady=(15, 5))

        # ── Output Directory ──
        ctk.CTkLabel(scroll, text="Output Directory", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        dir_frame = ctk.CTkFrame(scroll)
        dir_frame.pack(fill="x", padx=15, pady=2)

        self._dir_var = ctk.StringVar(value=self._config.output_dir)
        ctk.CTkEntry(
            dir_frame, textvariable=self._dir_var, width=350, font=("Consolas", 11)
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            dir_frame, text="Browse", width=70, command=self._browse
        ).pack(side="left")

        # ── Buttons ──
        self._btn_frame = ctk.CTkFrame(self)
        self._btn_frame.pack(fill="x", padx=20, pady=(0, 15))

        self._save_btn = ctk.CTkButton(
            self._btn_frame, text="Save", width=100, command=self._save
        )
        self._save_btn.pack(side="right", padx=5)
        self._cancel_btn = ctk.CTkButton(
            self._btn_frame, text="Cancel", width=100, fg_color="gray",
            command=self._cancel
        )
        self._cancel_btn.pack(side="right", padx=5)

    def _on_model_changed(self, name: str) -> None:
        self._update_model_hint(name)

    def _update_model_hint(self, name: str) -> None:
        if is_hf_custom_model(name):
            if is_model_downloaded(name):
                self._model_hint.configure(text="Korean model (converted, ready)", text_color="green")
            else:
                self._model_hint.configure(
                    text="Korean model — will download & convert on Save", text_color="#e07800"
                )
        else:
            self._model_hint.configure(text="")

    def _browse(self) -> None:
        path = filedialog.askdirectory(
            initialdir=self._config.output_dir,
            title="Select Output Directory",
        )
        if path:
            self._dir_var.set(path)

    def _save(self) -> None:
        new_model = self._model_var.get()
        if is_hf_custom_model(new_model) and not is_model_downloaded(new_model):
            self._start_download(new_model)
            return
        self._apply_and_close()

    def _apply_and_close(self) -> None:
        self._config.audio_source = self._source_var.get()
        self._config.model_name = self._model_var.get()
        self._config.compute_type = self._compute_var.get()
        self._config.device = self._device_var.get()
        self._config.language = self._lang_var.get()
        self._config.vad_filter = self._vad_var.get()
        self._config.output_dir = self._dir_var.get()
        self._config_manager.save()
        log.info("Settings saved")
        self.grab_release()
        self.destroy()

    def _start_download(self, model_name: str) -> None:
        """Expand window, show progress, and download + convert the model."""
        self.geometry("550x640")

        self._save_btn.configure(state="disabled")
        self._cancel_btn.configure(state="disabled")

        if self._dl_frame:
            self._dl_frame.destroy()

        self._dl_frame = ctk.CTkFrame(self)
        self._dl_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            self._dl_frame,
            text=f"Downloading model '{model_name}'",
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(10, 2))

        self._dl_status = ctk.CTkLabel(
            self._dl_frame,
            text="Starting...",
            font=("Segoe UI", 11),
            text_color="gray",
        )
        self._dl_status.pack(pady=4)

        self._dl_bar = ctk.CTkProgressBar(self._dl_frame, width=460)
        self._dl_bar.pack(pady=(4, 10))
        self._dl_bar.configure(mode="indeterminate")
        self._dl_bar.start()

        threading.Thread(
            target=self._download_bg, args=(model_name,), daemon=True
        ).start()

    def _download_bg(self, model_name: str) -> None:
        def set_status(text: str) -> None:
            self.after(0, lambda: self._dl_status.configure(text=text))

        try:
            download_model(model_name, progress_callback=set_status)
            self.after(0, self._download_complete)
        except Exception as exc:
            log.error("Model download/conversion failed", exc_info=True)
            self.after(0, lambda: self._download_failed(str(exc)))

    def _download_complete(self) -> None:
        self._dl_bar.stop()
        self._dl_bar.set(1)
        self._dl_bar.configure(mode="determinate")
        self._dl_status.configure(text="Done! Saving settings...", text_color="green")
        self.after(600, self._apply_and_close)

    def _download_failed(self, error: str) -> None:
        self._dl_bar.stop()
        self._dl_bar.set(0)
        short_error = error.splitlines()[0][:80]
        self._dl_status.configure(text=f"Error: {short_error}", text_color="red")
        self._save_btn.configure(state="normal")
        self._cancel_btn.configure(state="normal")

    def _cancel(self) -> None:
        self.grab_release()
        self.destroy()
