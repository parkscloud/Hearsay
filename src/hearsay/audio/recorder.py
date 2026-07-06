"""AudioRecorder thread: captures loopback and/or microphone audio in chunks."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from hearsay.audio.resampler import resample
from hearsay.constants import (
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MIC,
    AUDIO_SOURCE_SYSTEM,
    CHUNK_DURATION_S,
    OVERLAP_DURATION_S,
    SAMPLE_RATE,
    SILENCE_RMS_FLOOR,
)
from hearsay.utils.threading_utils import StoppableThread

log = logging.getLogger(__name__)

# Device-open retry policy: PortAudio -9999 "Unanticipated host error" is
# typically a transient device-busy state (e.g. the previous session's
# stream still being released by the OS).
_OPEN_ATTEMPTS = 5
_OPEN_RETRY_DELAY_S = 2.0

_OVERLAP_SAMPLES = int(OVERLAP_DURATION_S * SAMPLE_RATE)

# Windows shorter than this are dropped (Whisper hallucinates on slivers).
_MIN_WINDOW_SAMPLES = SAMPLE_RATE  # 1 second

_FRAMES_PER_BUFFER = 512


@dataclass
class AudioChunk:
    """One wall-clock window of captured audio, split per source.

    parts maps source name ('system'/'microphone') to 16kHz mono float32
    audio, ordered system-first so the pipeline can use the system text
    to filter microphone echo. Sources that were silent for the whole
    window are omitted.
    """

    index: int
    window_start: float  # seconds since recording started
    parts: dict[str, np.ndarray]


class _SourceBuffer:
    """Thread-safe frame accumulator for one capture stream.

    Capture callbacks append; the recorder thread cuts a window every
    CHUNK_DURATION_S. Each cut is prefixed with the previous window's
    tail (OVERLAP_DURATION_S) so words spanning a boundary transcribe
    intact; the pipeline strips the duplicated text afterwards.
    """

    def __init__(self, source: str, overlap_samples: int = _OVERLAP_SAMPLES) -> None:
        self.source = source
        self._overlap = overlap_samples
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._tail = np.empty(0, dtype=np.float32)

    def append(self, mono: np.ndarray) -> None:
        with self._lock:
            self._frames.append(mono)

    def cut(self) -> np.ndarray:
        """Drain buffered audio; empty when nothing arrived since the last cut."""
        with self._lock:
            if not self._frames:
                return np.empty(0, dtype=np.float32)
            new = np.concatenate(self._frames)
            self._frames.clear()
            data = np.concatenate([self._tail, new]) if len(self._tail) else new
            if self._overlap > 0:
                self._tail = data[-self._overlap:].copy()
            return data


class AudioRecorder(StoppableThread):
    """Record audio and push per-source AudioChunk windows to a queue.

    All capture is callback-driven; the thread's own loop only waits on
    the stop event and cuts a window every CHUNK_DURATION_S of wall
    clock, so stop() takes effect within ~0.5s even when no system audio
    is playing (blocking loopback reads used to hang for tens of seconds).

    Args:
        audio_queue: Queue to push AudioChunk objects.
        source: One of 'system', 'microphone', 'both'.
        loopback_device_index: PyAudioWPatch device index for loopback.
        mic_device_index: sounddevice device index for mic.
        on_fatal: Called from this thread when recording dies and no
            further audio will be captured. Not called for user stops.
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        source: str = AUDIO_SOURCE_SYSTEM,
        loopback_device_index: int | None = None,
        mic_device_index: int | None = None,
        loopback_channels: int = 2,
        loopback_rate: int = 48000,
        mic_channels: int = 1,
        mic_rate: int = 44100,
        on_fatal: Callable[[Exception], None] | None = None,
    ) -> None:
        super().__init__(name="AudioRecorder")
        self.audio_queue = audio_queue
        self.source = source
        self.loopback_device_index = loopback_device_index
        self.mic_device_index = mic_device_index
        self.loopback_channels = loopback_channels
        self.loopback_rate = loopback_rate
        self.mic_channels = mic_channels
        self.mic_rate = mic_rate
        self.on_fatal = on_fatal

    def run(self) -> None:
        log.info("AudioRecorder started (source=%s)", self.source)
        try:
            if self.source == AUDIO_SOURCE_SYSTEM:
                self._record_loopback()
            elif self.source == AUDIO_SOURCE_MIC:
                self._record_mic()
            elif self.source == AUDIO_SOURCE_BOTH:
                self._record_both()
            else:
                raise ValueError(f"Unknown audio source: {self.source!r}")
        except Exception as exc:
            log.error("AudioRecorder crashed", exc_info=True)
            if not self.stopped() and self.on_fatal is not None:
                try:
                    self.on_fatal(exc)
                except Exception:
                    log.error("on_fatal callback failed", exc_info=True)
        log.info("AudioRecorder stopped")

    # ── Capture modes ──────────────────────────────────────────────

    def _record_loopback(self) -> None:
        """Record system audio via WASAPI loopback (callback mode)."""
        import pyaudiowpatch as pyaudio

        p = pyaudio.PyAudio()
        try:
            self._resolve_loopback_device()
            buf = _SourceBuffer(AUDIO_SOURCE_SYSTEM)
            stream = self._open_loopback_stream(p, buf)
            try:
                self._capture_windows([buf], [stream])
            finally:
                self._close_stream(stream)
        finally:
            p.terminate()

    def _record_mic(self) -> None:
        """Record microphone via sounddevice (callback mode)."""
        import sounddevice as sd

        buf = _SourceBuffer(AUDIO_SOURCE_MIC)
        rate, channels = self.mic_rate, self.mic_channels

        def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            try:
                buf.append(resample(indata.copy(), rate, channels))
            except Exception:
                log.error("Error in mic callback", exc_info=True)

        stream = self._open_with_retry(
            lambda: sd.InputStream(
                device=self.mic_device_index,
                samplerate=rate,
                channels=channels,
                dtype="float32",
                callback=callback,
            ),
            what="microphone stream",
        )
        with stream:
            self._capture_windows([buf], [stream])

    def _record_both(self) -> None:
        """Record system audio and microphone as separate tagged streams.

        Both streams are opened through the same PyAudioWPatch (PortAudio)
        instance to avoid the COM/PortAudio initialisation conflict that
        occurs when PyAudioWPatch and sounddevice run on the same thread.
        Nothing is mixed: each source keeps its own buffer and the
        pipeline transcribes them separately so transcripts can label who
        was speaking. If one device fails, recording continues with the
        other rather than losing the session.
        """
        import pyaudiowpatch as pyaudio

        p = pyaudio.PyAudio()
        try:
            buffers: list[_SourceBuffer] = []
            streams: list[Any] = []
            try:
                self._resolve_loopback_device()
                lb_buf = _SourceBuffer(AUDIO_SOURCE_SYSTEM)
                streams.append(self._open_loopback_stream(p, lb_buf))
                buffers.append(lb_buf)
            except Exception:
                log.error(
                    "System-audio capture unavailable — continuing with mic only",
                    exc_info=True,
                )

            mic_buf = _SourceBuffer(AUDIO_SOURCE_MIC)
            try:
                streams.append(self._open_mic_stream_pyaudio(p, mic_buf))
                buffers.append(mic_buf)
            except Exception:
                log.error(
                    "Microphone capture unavailable — continuing with system audio only",
                    exc_info=True,
                )

            if not buffers:
                raise RuntimeError("Neither system audio nor microphone could be opened")

            try:
                self._capture_windows(buffers, streams)
            finally:
                for stream in streams:
                    self._close_stream(stream)
        finally:
            p.terminate()

    # ── Stream helpers ─────────────────────────────────────────────

    def _resolve_loopback_device(self) -> None:
        if self.loopback_device_index is not None:
            return
        from hearsay.audio.devices import get_default_loopback

        dev = get_default_loopback()
        if dev is None:
            raise RuntimeError("No loopback device found")
        self.loopback_device_index = dev.index
        self.loopback_channels = dev.channels
        self.loopback_rate = dev.sample_rate

    def _open_loopback_stream(self, p: Any, buf: _SourceBuffer) -> Any:
        import pyaudiowpatch as pyaudio

        rate, channels = self.loopback_rate, self.loopback_channels

        def callback(in_data, frame_count, time_info, status_flags):
            try:
                audio = np.frombuffer(in_data, dtype=np.int16)
                buf.append(resample(audio, rate, channels))
            except Exception:
                log.error("Error in loopback callback", exc_info=True)
            return (None, pyaudio.paContinue)

        return self._open_with_retry(
            lambda: p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=self.loopback_device_index,
                frames_per_buffer=_FRAMES_PER_BUFFER,
                stream_callback=callback,
            ),
            what="system-audio (loopback) stream",
        )

    def _open_mic_stream_pyaudio(self, p: Any, buf: _SourceBuffer) -> Any:
        import pyaudiowpatch as pyaudio

        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        mic_dev_index = wasapi_info.get("defaultInputDevice", -1)
        if mic_dev_index < 0:
            raise RuntimeError("No default WASAPI input device")

        mic_dev = p.get_device_info_by_index(mic_dev_index)
        mic_channels = max(1, mic_dev["maxInputChannels"])
        mic_rate = int(mic_dev["defaultSampleRate"])
        log.info(
            "Mic device for 'Both': %s (index=%d, ch=%d, rate=%d)",
            mic_dev["name"], mic_dev_index, mic_channels, mic_rate,
        )

        def callback(in_data, frame_count, time_info, status_flags):
            try:
                audio = np.frombuffer(in_data, dtype=np.int16)
                buf.append(resample(audio, mic_rate, mic_channels))
            except Exception:
                log.error("Error in mic callback", exc_info=True)
            return (None, pyaudio.paContinue)

        return self._open_with_retry(
            lambda: p.open(
                format=pyaudio.paInt16,
                channels=mic_channels,
                rate=mic_rate,
                input=True,
                input_device_index=mic_dev_index,
                frames_per_buffer=_FRAMES_PER_BUFFER,
                stream_callback=callback,
            ),
            what="microphone stream",
        )

    def _open_with_retry(self, open_fn: Callable[[], Any], what: str) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, _OPEN_ATTEMPTS + 1):
            try:
                return open_fn()
            except Exception as exc:
                last_exc = exc
                log.warning(
                    "Opening %s failed (attempt %d/%d): %s",
                    what, attempt, _OPEN_ATTEMPTS, exc,
                )
                if attempt < _OPEN_ATTEMPTS and self.wait(timeout=_OPEN_RETRY_DELAY_S):
                    break  # stop requested while retrying
        raise RuntimeError(
            f"Could not open {what} after {_OPEN_ATTEMPTS} attempts"
        ) from last_exc

    @staticmethod
    def _close_stream(stream: Any) -> None:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            log.debug("Error closing stream", exc_info=True)

    @staticmethod
    def _stream_active(stream: Any) -> bool:
        try:
            if hasattr(stream, "is_active"):
                return bool(stream.is_active())
            return bool(getattr(stream, "active", True))
        except Exception:
            return False

    # ── Window cutting ─────────────────────────────────────────────

    def _capture_windows(self, buffers: list[_SourceBuffer], streams: list[Any]) -> None:
        """Cut a window from every source buffer each CHUNK_DURATION_S of wall clock."""
        session_start = time.monotonic()
        window_open = 0.0  # elapsed seconds when the current window began
        chunk_index = 0
        dead_warned: set[int] = set()

        while not self.stopped():
            self.wait(timeout=0.5)

            for i, stream in enumerate(streams):
                if i not in dead_warned and not self._stream_active(stream):
                    dead_warned.add(i)
                    log.warning("Capture stream %d (%s) is no longer active",
                                i, buffers[i].source if i < len(buffers) else "?")
            if streams and len(dead_warned) == len(streams) and not self.stopped():
                raise RuntimeError("All capture streams stopped unexpectedly")

            elapsed = time.monotonic() - session_start
            if elapsed - window_open < CHUNK_DURATION_S:
                continue
            self._emit_window(buffers, chunk_index, window_open)
            chunk_index += 1
            window_open = elapsed

        # Flush the final partial window so the tail of the recording isn't lost.
        self._emit_window(buffers, chunk_index, window_open)

    def _emit_window(
        self,
        buffers: list[_SourceBuffer],
        chunk_index: int,
        window_start: float,
    ) -> None:
        parts: dict[str, np.ndarray] = {}
        for buf in buffers:
            data = buf.cut()
            if len(data) < _MIN_WINDOW_SAMPLES:
                continue
            rms = float(np.sqrt(np.mean(np.square(data, dtype=np.float64))))
            if rms < SILENCE_RMS_FLOOR:
                continue
            parts[buf.source] = data

        if not parts:
            return

        chunk = AudioChunk(index=chunk_index, window_start=window_start, parts=parts)
        log.debug(
            "Window %d queued (start=%.0fs, %s)",
            chunk_index, window_start,
            ", ".join(f"{s}={len(a)}" for s, a in parts.items()),
        )
        while True:
            try:
                self.audio_queue.put(chunk, timeout=0.5)
                return
            except queue.Full:
                if self.stopped():
                    # One final non-blocking attempt so stop never hangs here.
                    try:
                        self.audio_queue.put_nowait(chunk)
                    except queue.Full:
                        log.warning("Audio queue full at stop; dropped window %d", chunk_index)
                    return
