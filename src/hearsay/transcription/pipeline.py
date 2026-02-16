"""TranscriptionPipeline thread: consumes audio chunks, produces transcript text."""

from __future__ import annotations

import logging
import queue
import string
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

    _TAIL_WORD_COUNT = 15  # words kept from previous chunk for overlap matching
    _MIN_MATCH_WORDS = 2   # minimum overlap length to avoid false positives

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
        self._prev_tail_words: list[str] = []

    def run(self) -> None:
        log.info("TranscriptionPipeline started")
        while not self.stopped():
            try:
                chunk_index, audio = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._process_chunk(chunk_index, audio)

        # Drain any audio chunks still in the queue after stop signal.
        # The recorder flushes its buffer before exiting, so these chunks
        # must be transcribed to avoid losing the tail of the recording.
        log.info("TranscriptionPipeline draining remaining audio chunks")
        while True:
            try:
                chunk_index, audio = self.audio_queue.get_nowait()
            except queue.Empty:
                break
            self._process_chunk(chunk_index, audio)

        log.info("TranscriptionPipeline stopped")

    def _process_chunk(self, chunk_index: int, audio) -> None:
        """Transcribe a single audio chunk and enqueue the result."""
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
                original_words = result.text.split()
                if chunk_index > 0 and self._prev_tail_words:
                    result = self._deduplicate(result)
                self._prev_tail_words = original_words[-self._TAIL_WORD_COUNT:]
                if result.text:
                    self.transcript_queue.put(result)
        except Exception:
            log.error("Transcription failed for chunk %d", chunk_index, exc_info=True)

    @staticmethod
    def _normalize(word: str) -> str:
        """Strip leading/trailing punctuation for comparison."""
        return word.strip(string.punctuation)

    def _deduplicate(self, result: TranscriptionResult) -> TranscriptionResult:
        """Remove overlapping prefix from *result* that duplicates the tail of the previous chunk."""
        new_words = result.text.split()
        if len(new_words) < self._MIN_MATCH_WORDS:
            return result

        # Find the longest prefix of new_words that matches a suffix of _prev_tail_words.
        best = 0
        for length in range(self._MIN_MATCH_WORDS, min(len(self._prev_tail_words), len(new_words)) + 1):
            suffix = self._prev_tail_words[-length:]
            prefix = new_words[:length]
            tail = [self._normalize(w).lower() for w in suffix]
            head = [self._normalize(w).lower() for w in prefix]
            # All words after the first must match exactly; the first word of the
            # new chunk may be truncated (e.g. "replaced" -> "placed") so allow a
            # suffix-of-word match when the fragment is at least 3 characters.
            first_ok = tail[0] == head[0] or (len(head[0]) >= 3 and tail[0].endswith(head[0]))
            if first_ok and tail[1:] == head[1:]:
                best = length

        if best == 0:
            return result

        stripped_words = new_words[best:]
        log.info(
            "Chunk %d: stripped %d overlapping words: %s",
            result.chunk_index,
            best,
            " ".join(new_words[:best]),
        )

        if not stripped_words:
            return TranscriptionResult(
                text="",
                segments=[],
                language=result.language,
                language_probability=result.language_probability,
                chunk_index=result.chunk_index,
            )

        # Rebuild text and trim leading segments that were fully covered by the overlap.
        new_text = " ".join(stripped_words)
        chars_removed = len(" ".join(new_words[:best])) + 1  # +1 for the space after
        trimmed_segments = []
        for seg in result.segments:
            seg_text = seg["text"]
            if chars_removed >= len(seg_text):
                chars_removed -= len(seg_text) + 1  # +1 for joining space
                continue
            if chars_removed > 0:
                seg = {**seg, "text": seg_text[chars_removed:].lstrip()}
                chars_removed = 0
            trimmed_segments.append(seg)

        return TranscriptionResult(
            text=new_text,
            segments=trimmed_segments if trimmed_segments else result.segments,
            language=result.language,
            language_probability=result.language_probability,
            chunk_index=result.chunk_index,
        )
