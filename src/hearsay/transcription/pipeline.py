"""TranscriptionPipeline thread: consumes audio chunks, produces transcript text."""

from __future__ import annotations

import logging
import queue
import time

from hearsay.transcription.engine import TranscriptionEngine, TranscriptionResult
from hearsay.utils.threading_utils import StoppableThread

log = logging.getLogger(__name__)


class TranscriptionPipeline(StoppableThread):
    """Daemon thread that reads audio chunks from audio_queue,
    transcribes them, and pushes results to transcript_queue.

    Args:
        audio_queue: Input queue of (chunk_index, np.ndarray) tuples.
        transcript_queue: Output queue of TranscriptionResult objects.
        engine: Configured TranscriptionEngine (model already loaded).
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        transcript_queue: queue.Queue,
        engine: TranscriptionEngine,
    ) -> None:
        super().__init__(name="TranscriptionPipeline")
        self.audio_queue = audio_queue
        self.transcript_queue = transcript_queue
        self.engine = engine

    def run(self) -> None:
        log.info("TranscriptionPipeline started")
        while not self.stopped():
            try:
                chunk_index, audio = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                t0 = time.perf_counter()
                result = self.engine.transcribe(audio, chunk_index=chunk_index)
                elapsed = time.perf_counter() - t0
                log.info(
                    "Chunk %d transcribed in %.1fs: %s",
                    chunk_index,
                    elapsed,
                    result.text[:80] if result.text else "(empty)",
                )
                if result.text:
                    self.transcript_queue.put(result)
            except Exception:
                log.error("Transcription failed for chunk %d", chunk_index, exc_info=True)

        log.info("TranscriptionPipeline stopped")
