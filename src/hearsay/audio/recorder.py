"""AudioRecorder thread: captures loopback and/or microphone audio in chunks."""

from __future__ import annotations

import logging
import queue
from typing import Callable

import numpy as np

from hearsay.audio.mixer import mix_streams
from hearsay.audio.resampler import resample
from hearsay.constants import (
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MIC,
    AUDIO_SOURCE_SYSTEM,
    MAX_CHUNK_DURATION_S,
    MIN_CHUNK_DURATION_S,
    OVERLAP_DURATION_S,
    SAMPLE_RATE,
    SILENCE_DURATION_S,
    SILENCE_RMS_THRESHOLD,
)
from hearsay.utils.threading_utils import StoppableThread

log = logging.getLogger(__name__)


class _ChunkAccumulator:
    """Accumulates mono 16 kHz float32 audio and decides chunk boundaries.

    A chunk becomes ready when either:
      * the buffer reaches ``MAX_CHUNK_DURATION_S`` (hard cap), or
      * at least ``MIN_CHUNK_DURATION_S`` has accumulated AND the trailing
        ``SILENCE_DURATION_S`` of audio is near-silent.

    Consecutive chunks share ``OVERLAP_DURATION_S`` of audio so the
    transcription pipeline can stitch words across boundaries.  Each emitted
    chunk carries its absolute start time (seconds from the start of the
    recording), so downstream timestamps stay correct despite variable lengths.
    """

    def __init__(self) -> None:
        self._buffer: list[np.ndarray] = []
        self._total = 0          # samples currently buffered
        self._silence_run = 0    # consecutive trailing near-silent samples
        self._start_sample = 0   # absolute index of buffer[0] in the recording
        self.chunk_index = 0

        self._min = int(MIN_CHUNK_DURATION_S * SAMPLE_RATE)
        self._max = int(MAX_CHUNK_DURATION_S * SAMPLE_RATE)
        self._silence_needed = int(SILENCE_DURATION_S * SAMPLE_RATE)
        self._overlap = int(OVERLAP_DURATION_S * SAMPLE_RATE)

    def add(self, mono: np.ndarray, silent: bool | None = None) -> None:
        """Append a mono frame, updating the trailing-silence run.

        If *silent* is None, silence is computed from this frame's RMS.
        Callers mixing multiple sources (Both mode) pass an explicit flag.
        """
        if mono is None or len(mono) == 0:
            return
        self._buffer.append(mono)
        self._total += len(mono)

        if silent is None:
            rms = float(np.sqrt(np.mean(mono ** 2)))
            silent = rms < SILENCE_RMS_THRESHOLD

        if silent:
            self._silence_run += len(mono)
        else:
            self._silence_run = 0

    def ready(self) -> bool:
        """True when the current buffer should be emitted as a chunk."""
        if self._total >= self._max:
            return True
        return self._total >= self._min and self._silence_run >= self._silence_needed

    def pop(self) -> tuple[int, float, np.ndarray]:
        """Emit a chunk and retain the overlap tail. Returns (index, start_s, audio)."""
        data = np.concatenate(self._buffer)
        emitted_len = min(len(data), self._max)
        chunk = data[:emitted_len]
        start_time = self._start_sample / SAMPLE_RATE
        idx = self.chunk_index

        # Advance by the unique (non-overlapping) audio we just consumed.
        advance = max(0, emitted_len - self._overlap)
        self._start_sample += advance

        if self._overlap > 0:
            leftover = data[emitted_len - self._overlap:]
        else:
            leftover = data[emitted_len:]
        self._buffer = [leftover] if len(leftover) else []
        self._total = int(len(leftover))
        self._silence_run = 0
        self.chunk_index += 1
        return idx, start_time, chunk

    def flush(self) -> tuple[int, float, np.ndarray] | None:
        """Emit whatever remains (if > 1s) when recording stops."""
        if self._total <= SAMPLE_RATE:  # less than 1 second — discard
            return None
        data = np.concatenate(self._buffer)
        start_time = self._start_sample / SAMPLE_RATE
        idx = self.chunk_index
        self._buffer = []
        self._total = 0
        self.chunk_index += 1
        return idx, start_time, data


def _rms(mono: np.ndarray) -> float:
    """Root-mean-square level of a mono float32 frame."""
    if mono is None or len(mono) == 0:
        return 0.0
    return float(np.sqrt(np.mean(mono ** 2)))


class AudioRecorder(StoppableThread):
    """Record audio and push variable-length chunks to a queue.

    Each queue item is a ``(chunk_index, start_time_s, np.ndarray)`` tuple,
    where ``start_time_s`` is the chunk's absolute offset from the start of the
    recording.

    When ``on_frame`` is provided, the recorder streams every mono 16 kHz
    float32 frame to that callback instead of accumulating chunks into
    ``audio_queue`` — used to feed RealtimeSTT continuously for low latency.

    Args:
        audio_queue: Queue to push chunks to (ignored when ``on_frame`` is set).
        source: One of 'system', 'microphone', 'both'.
        on_frame: Optional per-frame callback for streaming (RealtimeSTT) mode.
        loopback_device_index: PyAudioWPatch device index for loopback.
        mic_device_index: sounddevice device index for mic.
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        source: str = AUDIO_SOURCE_SYSTEM,
        on_frame: Callable[[np.ndarray], None] | None = None,
        loopback_device_index: int | None = None,
        mic_device_index: int | None = None,
        loopback_channels: int = 2,
        loopback_rate: int = 48000,
        mic_channels: int = 1,
        mic_rate: int = 44100,
    ) -> None:
        super().__init__(name="AudioRecorder")
        self.audio_queue = audio_queue
        self.source = source
        self.on_frame = on_frame
        self.loopback_device_index = loopback_device_index
        self.mic_device_index = mic_device_index
        self.loopback_channels = loopback_channels
        self.loopback_rate = loopback_rate
        self.mic_channels = mic_channels
        self.mic_rate = mic_rate

    def run(self) -> None:
        log.info("AudioRecorder started (source=%s)", self.source)
        try:
            if self.source == AUDIO_SOURCE_SYSTEM:
                self._record_loopback()
            elif self.source == AUDIO_SOURCE_MIC:
                self._record_mic()
            elif self.source == AUDIO_SOURCE_BOTH:
                self._record_both()
        except Exception:
            log.error("AudioRecorder crashed", exc_info=True)
        log.info("AudioRecorder stopped")

    def _record_loopback(self) -> None:
        """Record system audio via WASAPI loopback."""
        import pyaudiowpatch as pyaudio

        p = pyaudio.PyAudio()
        try:
            if self.loopback_device_index is None:
                from hearsay.audio.devices import get_default_loopback
                dev = get_default_loopback()
                if dev is None:
                    log.error("No loopback device found")
                    return
                self.loopback_device_index = dev.index
                self.loopback_channels = dev.channels
                self.loopback_rate = dev.sample_rate

            frames_per_buffer = 512
            stream = p.open(
                format=pyaudio.paInt16,
                channels=self.loopback_channels,
                rate=self.loopback_rate,
                input=True,
                input_device_index=self.loopback_device_index,
                frames_per_buffer=frames_per_buffer,
            )

            self._chunk_loop(
                read_fn=lambda: stream.read(frames_per_buffer, exception_on_overflow=False),
                sr=self.loopback_rate,
                channels=self.loopback_channels,
            )

            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()

    def _record_mic(self) -> None:
        """Record microphone via sounddevice."""
        import sounddevice as sd

        acc = _ChunkAccumulator()

        def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            mono = resample(indata.copy(), self.mic_rate, self.mic_channels)
            if self.on_frame is not None:
                self.on_frame(mono)
                return
            acc.add(mono)
            if acc.ready():
                self.audio_queue.put(acc.pop())

        with sd.InputStream(
            device=self.mic_device_index,
            samplerate=self.mic_rate,
            channels=self.mic_channels,
            dtype="float32",
            callback=callback,
        ):
            while not self.stopped():
                self.wait(timeout=0.5)

        if self.on_frame is not None:
            return

        final = acc.flush()
        if final is not None:
            self.audio_queue.put(final)

    def _record_both(self) -> None:
        """Record both loopback and mic, mix them.

        Both streams are opened through the same PyAudioWPatch (PortAudio)
        instance to avoid the COM/PortAudio initialisation conflict that
        occurs when PyAudioWPatch and sounddevice run on the same thread.
        The mic stream uses PyAudio's callback mode so it accumulates data
        asynchronously while the main loop drives off blocking loopback
        reads.  Chunk boundaries are decided on the *combined* activity, so a
        chunk is only cut when both sources fall silent.
        """
        import pyaudiowpatch as pyaudio

        p = pyaudio.PyAudio()
        try:
            # --- Loopback setup ---
            if self.loopback_device_index is None:
                from hearsay.audio.devices import get_default_loopback
                dev = get_default_loopback()
                if dev is None:
                    log.error("No loopback device found")
                    return
                self.loopback_device_index = dev.index
                self.loopback_channels = dev.channels
                self.loopback_rate = dev.sample_rate

            frames_per_buffer = 512
            loopback_stream = p.open(
                format=pyaudio.paInt16,
                channels=self.loopback_channels,
                rate=self.loopback_rate,
                input=True,
                input_device_index=self.loopback_device_index,
                frames_per_buffer=frames_per_buffer,
            )

            # --- Mic setup via same PyAudio instance ---
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            mic_dev_index = wasapi_info.get("defaultInputDevice", -1)
            if mic_dev_index < 0:
                log.error("No default WASAPI input device — recording loopback only")
                self._chunk_loop(
                    read_fn=lambda: loopback_stream.read(
                        frames_per_buffer, exception_on_overflow=False,
                    ),
                    sr=self.loopback_rate,
                    channels=self.loopback_channels,
                )
                loopback_stream.stop_stream()
                loopback_stream.close()
                return

            mic_dev = p.get_device_info_by_index(mic_dev_index)
            mic_channels = max(1, mic_dev["maxInputChannels"])
            mic_rate = int(mic_dev["defaultSampleRate"])
            log.info(
                "Mic device for 'Both': %s (index=%d, ch=%d, rate=%d)",
                mic_dev["name"], mic_dev_index, mic_channels, mic_rate,
            )

            mic_buffer: list[np.ndarray] = []

            def mic_callback(in_data, frame_count, time_info, status_flags):
                try:
                    audio = np.frombuffer(in_data, dtype=np.int16)
                    mono = resample(audio, mic_rate, mic_channels)
                    mic_buffer.append(mono)
                except Exception:
                    log.error("Error in mic callback", exc_info=True)
                return (None, pyaudio.paContinue)

            mic_stream = p.open(
                format=pyaudio.paInt16,
                channels=mic_channels,
                rate=mic_rate,
                input=True,
                input_device_index=mic_dev_index,
                frames_per_buffer=frames_per_buffer,
                stream_callback=mic_callback,
            )
            mic_stream.start_stream()

            # --- Main loop (driven by blocking loopback reads) ---
            acc = _ChunkAccumulator()

            def mix_with_mic(lb_chunk: np.ndarray) -> np.ndarray:
                if not mic_buffer:
                    return lb_chunk
                mic_chunk = np.concatenate(mic_buffer)[:len(lb_chunk)]
                if len(mic_chunk) < len(lb_chunk):
                    mic_chunk = np.pad(mic_chunk, (0, len(lb_chunk) - len(mic_chunk)))
                return mix_streams(lb_chunk, mic_chunk)

            while not self.stopped():
                try:
                    raw = loopback_stream.read(frames_per_buffer, exception_on_overflow=False)
                except Exception:
                    break
                audio = np.frombuffer(raw, dtype=np.int16)
                lb_mono = resample(audio, self.loopback_rate, self.loopback_channels)

                if self.on_frame is not None:
                    self.on_frame(mix_with_mic(lb_mono))
                    mic_buffer.clear()
                    continue

                # Combined silence: silent only when both sources are quiet.
                # The latest mic frame approximates current mic activity.
                mic_silent = _rms(mic_buffer[-1]) < SILENCE_RMS_THRESHOLD if mic_buffer else True
                silent = (_rms(lb_mono) < SILENCE_RMS_THRESHOLD) and mic_silent

                acc.add(lb_mono, silent=silent)
                if acc.ready():
                    idx, start_time, lb_chunk = acc.pop()
                    self.audio_queue.put((idx, start_time, mix_with_mic(lb_chunk)))
                    mic_buffer.clear()

            # --- Flush remaining audio ---
            if self.on_frame is None:
                final = acc.flush()
                if final is not None:
                    idx, start_time, lb_chunk = final
                    self.audio_queue.put((idx, start_time, mix_with_mic(lb_chunk)))

            mic_stream.stop_stream()
            mic_stream.close()
            loopback_stream.stop_stream()
            loopback_stream.close()
        finally:
            p.terminate()

    def _chunk_loop(
        self,
        read_fn: callable,
        sr: int,
        channels: int,
    ) -> None:
        """Generic chunking loop for loopback-style (blocking-read) streams."""
        acc = _ChunkAccumulator()

        while not self.stopped():
            try:
                raw = read_fn()
            except Exception:
                break
            audio = np.frombuffer(raw, dtype=np.int16)
            mono = resample(audio, sr, channels)

            if self.on_frame is not None:
                self.on_frame(mono)
                continue

            acc.add(mono)

            if acc.ready():
                idx, start_time, chunk = acc.pop()
                self.audio_queue.put((idx, start_time, chunk))
                log.debug(
                    "Audio chunk %d queued (%d samples, t=%.1fs)",
                    idx, len(chunk), start_time,
                )

        if self.on_frame is not None:
            return

        final = acc.flush()
        if final is not None:
            idx, start_time, chunk = final
            self.audio_queue.put((idx, start_time, chunk))
            log.debug("Final audio chunk %d queued (%d samples)", idx, len(chunk))
