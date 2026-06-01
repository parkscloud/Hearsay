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

    def __init__(
        self,
        master: ctk.CTk,
        config_manager: ConfigManager,
        on_save: "Callable | None" = None,
    ) -> None:
        super().__init__(master)
        self.title(f"{APP_NAME} Settings")
        self.geometry("550x620")
        self.resizable(False, False)

        self._config_manager = config_manager
        self._config = config_manager.config
        self._dl_frame: ctk.CTkFrame | None = None
        self._on_save = on_save
        self._capturing = False

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
        scroll = ctk.CTkScrollableFrame(self, width=490, height=460)
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

        # ── Hotkey ──
        ctk.CTkLabel(scroll, text="Recording Hotkey", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        hotkey_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        hotkey_frame.pack(anchor="w", padx=15, fill="x")

        self._hotkey_var = ctk.StringVar(value=self._config.hotkey)
        self._hotkey_entry = ctk.CTkEntry(
            hotkey_frame, textvariable=self._hotkey_var, width=200, state="readonly"
        )
        self._hotkey_entry.pack(side="left", padx=(0, 8))
        self._capture_btn = ctk.CTkButton(
            hotkey_frame, text="Capture", width=80, command=self._start_capture
        )
        self._capture_btn.pack(side="left")
        ctk.CTkLabel(
            scroll, text="Press Ctrl+Alt+R or any modifier+key combo",
            font=("Segoe UI", 10), text_color="gray"
        ).pack(anchor="w", padx=15)

        # ── Beep Notifications ──
        ctk.CTkLabel(scroll, text="Beep Notifications", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        self._beep_start_var = ctk.BooleanVar(value=self._config.beep_on_start)
        self._beep_stop_var = ctk.BooleanVar(value=self._config.beep_on_stop)
        self._beep_save_var = ctk.BooleanVar(value=self._config.beep_on_save)
        ctk.CTkCheckBox(
            scroll, text="녹음 시작 시 비프음", variable=self._beep_start_var
        ).pack(anchor="w", padx=15, pady=2)
        ctk.CTkCheckBox(
            scroll, text="녹음 완료 시 비프음", variable=self._beep_stop_var
        ).pack(anchor="w", padx=15, pady=2)
        ctk.CTkCheckBox(
            scroll, text="MD 파일 저장 완료 시 비프음", variable=self._beep_save_var
        ).pack(anchor="w", padx=15, pady=2)

        # ── Clipboard ──
        ctk.CTkLabel(scroll, text="Clipboard", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(15, 5)
        )
        self._clipboard_var = ctk.BooleanVar(value=self._config.copy_to_clipboard)
        ctk.CTkCheckBox(
            scroll,
            text="저장 완료 시 전체 텍스트를 클립보드에 복사",
            variable=self._clipboard_var,
        ).pack(anchor="w", padx=15, pady=2)

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

    def _start_capture(self) -> None:
        self._capturing = True
        self._hotkey_entry.configure(state="normal")
        self._hotkey_var.set("Press hotkey...")
        self._hotkey_entry.configure(state="readonly")
        self._capture_btn.configure(text="Cancel", command=self._cancel_capture)
        self._hotkey_entry.focus_set()
        self.bind("<KeyPress>", self._on_key_capture)

    def _cancel_capture(self) -> None:
        self._capturing = False
        self.unbind("<KeyPress>")
        self._hotkey_entry.configure(state="normal")
        self._hotkey_var.set(self._config.hotkey)
        self._hotkey_entry.configure(state="readonly")
        self._capture_btn.configure(text="Capture", command=self._start_capture)

    def _on_key_capture(self, event) -> str:
        keysym = event.keysym.lower()
        modifier_only = {
            "control_l", "control_r", "alt_l", "alt_r",
            "shift_l", "shift_r", "super_l", "super_r",
        }
        if keysym in modifier_only:
            return "break"
        if keysym == "escape":
            self._cancel_capture()
            return "break"

        parts = []
        if event.state & 0x4:       # Ctrl
            parts.append("ctrl")
        if event.state & 0x1:       # Shift
            parts.append("shift")
        if event.state & 0x20000:   # Alt (Windows)
            parts.append("alt")

        if not parts:
            return "break"          # require at least one modifier

        parts.append(keysym)
        combo = "+".join(parts)

        self._capturing = False
        self.unbind("<KeyPress>")
        self._hotkey_entry.configure(state="normal")
        self._hotkey_var.set(combo)
        self._hotkey_entry.configure(state="readonly")
        self._capture_btn.configure(text="Capture", command=self._start_capture)
        return "break"

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
        self._config.hotkey = self._hotkey_var.get()
        self._config.beep_on_start = self._beep_start_var.get()
        self._config.beep_on_stop = self._beep_stop_var.get()
        self._config.beep_on_save = self._beep_save_var.get()
        self._config.copy_to_clipboard = self._clipboard_var.get()
        self._config_manager.save()
        log.info("Settings saved")
        self.grab_release()
        self.destroy()
        if self._on_save:
            self._on_save()

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
