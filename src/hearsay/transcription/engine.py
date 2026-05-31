"""TranscriptionEngine: wraps faster-whisper for inference."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from hearsay.utils.paths import get_models_dir

log = logging.getLogger(__name__)


class CudaUnavailableError(RuntimeError):
    """Raised when GPU is configured but CUDA runtime DLLs are missing."""


@dataclass
class TranscriptionResult:
    """Result from transcribing one audio chunk."""

    text: str
    segments: list[dict]  # [{start, end, text}, ...]
    language: str
    language_probability: float
    chunk_index: int
    start_time: float = 0.0  # absolute offset (s) of this chunk from recording start


class TranscriptionEngine:
    """Wraps faster-whisper WhisperModel for inference."""

    def __init__(
        self,
        model_name: str = "small.en",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
        vad_filter: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self._model = None

    def load(self) -> None:
        """Load the Whisper model into memory."""
        from faster_whisper import WhisperModel
        from hearsay.transcription.model_manager import resolve_model_path

        model_path = resolve_model_path(self.model_name)
        log.info(
            "Loading model '%s' (device=%s, compute=%s)",
            self.model_name,
            self.device,
            self.compute_type,
        )
        try:
            self._model = WhisperModel(
                model_path,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(get_models_dir()),
            )
        except RuntimeError as exc:
            if self.device != "cpu" and "cannot be loaded" in str(exc):
                raise CudaUnavailableError(str(exc)) from exc
            raise
        log.info("Model loaded successfully (device=%s)", self.device)

    def transcribe(
        self,
        audio: np.ndarray,
        chunk_index: int = 0,
        start_time: float = 0.0,
    ) -> TranscriptionResult:
        """Transcribe a float32 16kHz mono audio array.

        Args:
            audio: Audio data as float32 numpy array at 16kHz.
            chunk_index: Index of this chunk (for ordering).
            start_time: Absolute offset (s) of this chunk from recording start.

        Returns:
            TranscriptionResult with text and segment details.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        segments_iter, info = self._model.transcribe(
            audio,
            beam_size=5,
            language=self.language if self.language else None,
            vad_filter=self.vad_filter,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        segments = []
        texts = []
        for seg in segments_iter:
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })
            texts.append(seg.text.strip())

        full_text = " ".join(texts)
        log.debug(
            "Chunk %d: %d segments, lang=%s (%.2f), text=%s",
            chunk_index,
            len(segments),
            info.language,
            info.language_probability,
            full_text[:100],
        )

        return TranscriptionResult(
            text=full_text,
            segments=segments,
            language=info.language,
            language_probability=info.language_probability,
            chunk_index=chunk_index,
            start_time=start_time,
        )

    def unload(self) -> None:
        """Free model memory."""
        self._model = None
        log.info("Model unloaded")
