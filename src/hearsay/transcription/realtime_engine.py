"""RealtimeEngine: dual-layer transcription via RealtimeSTT.

Audio is captured by Hearsay's own AudioRecorder (system loopback / mic / both)
and fed into RealtimeSTT through ``feed_audio`` (``use_microphone=False``).  Two
whisper models run concurrently:

  * a fast *realtime* model drives the tentative ("typing") layer, revised
    continuously as the user speaks (``on_tentative``);
  * the accurate *main* model produces the final text once VAD detects the end
    of an utterance (``on_final``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np

from hearsay.transcription.model_manager import resolve_model_path
from hearsay.utils.paths import get_models_dir

log = logging.getLogger(__name__)


class CudaUnavailableError(RuntimeError):
    """Raised when GPU is configured but CUDA is not available."""


class RealtimeEngine:
    """Drives RealtimeSTT with externally fed audio and two output layers."""

    def __init__(
        self,
        model_name: str,
        realtime_model_name: str,
        device: str,
        compute_type: str,
        language: str,
        on_tentative: Callable[[str], None],
        on_final: Callable[[str], None],
        on_utterance_start: Callable[[], None] | None = None,
        post_speech_silence_duration: float = 0.7,
    ) -> None:
        self.model_name = model_name
        self.realtime_model_name = realtime_model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language or ""
        self._on_tentative = on_tentative
        self._on_final = on_final
        self._on_utterance_start = on_utterance_start
        self._post_speech_silence_duration = post_speech_silence_duration

        self._recorder = None
        self._final_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._final_emitted = threading.Event()

    def load(self) -> None:
        """Create the RealtimeSTT recorder (spawns the main-model process) and
        start the final-text loop. Blocks until both models are ready."""
        if self.device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    raise CudaUnavailableError("CUDA is not available")
            except CudaUnavailableError:
                raise
            except Exception as exc:  # torch import/init failure
                raise CudaUnavailableError(str(exc)) from exc

        from RealtimeSTT import AudioToTextRecorder

        model = resolve_model_path(self.model_name)
        log.info(
            "Loading RealtimeSTT (main=%s, realtime=%s, device=%s, compute=%s)",
            self.model_name, self.realtime_model_name, self.device, self.compute_type,
        )
        self._recorder = AudioToTextRecorder(
            model=model,
            realtime_model_type=self.realtime_model_name,
            language=self.language,
            device=self.device,
            compute_type=self.compute_type,
            download_root=str(get_models_dir()),
            use_microphone=False,
            enable_realtime_transcription=True,
            on_realtime_transcription_stabilized=self._handle_tentative,
            on_recording_start=self._handle_utterance_start,
            post_speech_silence_duration=self._post_speech_silence_duration,
            spinner=False,
            level=logging.WARNING,
            no_log_file=True,
        )
        log.info("RealtimeSTT ready")

        self._final_thread = threading.Thread(
            target=self._final_loop, daemon=True, name="RealtimeFinal",
        )
        self._final_thread.start()

    def feed(self, mono_float32: np.ndarray) -> None:
        """Feed one mono 16 kHz float32 frame into RealtimeSTT.

        ``feed_audio`` casts directly to int16 without scaling, so float [-1, 1]
        audio must be scaled into the int16 range first.
        """
        rec = self._recorder
        if rec is None or mono_float32 is None or len(mono_float32) == 0:
            return
        pcm16 = np.clip(mono_float32 * 32768.0, -32768, 32767).astype(np.int16)
        try:
            rec.feed_audio(pcm16, 16000)
        except Exception:
            log.error("feed_audio failed", exc_info=True)

    def _handle_tentative(self, text: str) -> None:
        if text and text.strip() and not self._stop.is_set():
            self._on_tentative(text.strip())

    def _handle_utterance_start(self) -> None:
        if self._on_utterance_start is not None and not self._stop.is_set():
            self._on_utterance_start()

    def _final_loop(self) -> None:
        """Block on recorder.text() and emit each finalized utterance."""
        while not self._stop.is_set():
            try:
                text = self._recorder.text()
            except Exception:
                if self._stop.is_set():
                    break
                log.error("RealtimeSTT text() failed", exc_info=True)
                break
            if text and text.strip():
                self._on_final(text.strip())
            self._final_emitted.set()
            if self._stop.is_set():
                break

    def shutdown(self) -> None:
        """Finalize any in-progress utterance, then tear down the recorder."""
        rec = self._recorder
        if rec is not None and getattr(rec, "is_recording", False):
            # Stopped mid-utterance: gracefully stop the active recording so its
            # buffered audio gets a final transcription instead of being dropped.
            started = getattr(rec, "recording_start_time", 0) or 0
            min_len = getattr(rec, "min_length_of_recording", 0.5)
            if not started or (time.time() - started) >= min_len:
                try:
                    self._final_emitted.clear()
                    rec.stop()
                    self._final_emitted.wait(timeout=15)
                except Exception:
                    log.warning("Error finalizing in-progress utterance", exc_info=True)

        self._stop.set()
        self._recorder = None
        if rec is not None:
            try:
                rec.shutdown()
            except Exception:
                log.warning("RealtimeSTT shutdown error", exc_info=True)
        if self._final_thread is not None:
            self._final_thread.join(timeout=10)
            self._final_thread = None
