"""AudioRecorder thread: captures loopback and/or microphone audio in chunks."""

from __future__ import annotations

import logging
import queue
import time

import numpy as np

from hearsay.audio.mixer import mix_streams
from hearsay.audio.resampler import resample
from hearsay.constants import (
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MIC,
    AUDIO_SOURCE_SYSTEM,
    CHUNK_DURATION_S,
    OVERLAP_DURATION_S,
    SAMPLE_RATE,
)
from hearsay.utils.threading_utils import StoppableThread

log = logging.getLogger(__name__)


class AudioRecorder(StoppableThread):
    """Record audio and push 30-second chunks to a queue.

    Args:
        audio_queue: Queue to push (chunk_index, np.ndarray) tuples.
        source: One of 'system', 'microphone', 'both'.
        loopback_device_index: PyAudioWPatch device index for loopback.
        mic_device_index: sounddevice device index for mic.
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

        buffer: list[np.ndarray] = []
        chunk_samples = int(CHUNK_DURATION_S * SAMPLE_RATE)
        overlap_samples = int(OVERLAP_DURATION_S * SAMPLE_RATE)
        chunk_index = 0

        def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            nonlocal chunk_index
            mono = resample(indata.copy(), self.mic_rate, self.mic_channels)
            buffer.append(mono)

            total = sum(len(b) for b in buffer)
            if total >= chunk_samples:
                chunk = np.concatenate(buffer)[:chunk_samples]
                self.audio_queue.put((chunk_index, chunk))
                chunk_index += 1
                # Keep overlap
                if overlap_samples > 0:
                    leftover = np.concatenate(buffer)[chunk_samples - overlap_samples:]
                    buffer.clear()
                    buffer.append(leftover)
                else:
                    buffer.clear()

        device = self.mic_device_index
        with sd.InputStream(
            device=device,
            samplerate=self.mic_rate,
            channels=self.mic_channels,
            dtype="float32",
            callback=callback,
        ):
            while not self.stopped():
                self.wait(timeout=0.5)

        # Flush remaining audio
        if buffer:
            chunk = np.concatenate(buffer)
            if len(chunk) > SAMPLE_RATE:  # Only if > 1 second
                self.audio_queue.put((chunk_index, chunk))

    def _record_both(self) -> None:
        """Record both loopback and mic, mix them."""
        import pyaudiowpatch as pyaudio
        import sounddevice as sd

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
            loopback_stream = p.open(
                format=pyaudio.paInt16,
                channels=self.loopback_channels,
                rate=self.loopback_rate,
                input=True,
                input_device_index=self.loopback_device_index,
                frames_per_buffer=frames_per_buffer,
            )

            mic_buffer: list[np.ndarray] = []

            def mic_callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
                mono = resample(indata.copy(), self.mic_rate, self.mic_channels)
                mic_buffer.append(mono)

            mic_stream = sd.InputStream(
                device=self.mic_device_index,
                samplerate=self.mic_rate,
                channels=self.mic_channels,
                dtype="float32",
                callback=mic_callback,
            )

            chunk_samples = int(CHUNK_DURATION_S * SAMPLE_RATE)
            overlap_samples = int(OVERLAP_DURATION_S * SAMPLE_RATE)
            loopback_buf: list[np.ndarray] = []
            chunk_index = 0

            with mic_stream:
                while not self.stopped():
                    try:
                        raw = loopback_stream.read(frames_per_buffer, exception_on_overflow=False)
                    except Exception:
                        break
                    audio = np.frombuffer(raw, dtype=np.int16)
                    mono = resample(audio, self.loopback_rate, self.loopback_channels)
                    loopback_buf.append(mono)

                    total = sum(len(b) for b in loopback_buf)
                    if total >= chunk_samples:
                        lb_chunk = np.concatenate(loopback_buf)[:chunk_samples]

                        if mic_buffer:
                            mic_chunk = np.concatenate(mic_buffer)[:chunk_samples]
                            if len(mic_chunk) < chunk_samples:
                                mic_chunk = np.pad(mic_chunk, (0, chunk_samples - len(mic_chunk)))
                            mixed = mix_streams(lb_chunk, mic_chunk)
                        else:
                            mixed = lb_chunk

                        self.audio_queue.put((chunk_index, mixed))
                        chunk_index += 1

                        if overlap_samples > 0:
                            leftover = np.concatenate(loopback_buf)[chunk_samples - overlap_samples:]
                            loopback_buf.clear()
                            loopback_buf.append(leftover)
                        else:
                            loopback_buf.clear()
                        mic_buffer.clear()

            # Flush remaining audio
            if loopback_buf:
                lb_chunk = np.concatenate(loopback_buf)
                if len(lb_chunk) > SAMPLE_RATE:  # Only if > 1 second
                    if mic_buffer:
                        mic_chunk = np.concatenate(mic_buffer)[:len(lb_chunk)]
                        if len(mic_chunk) < len(lb_chunk):
                            mic_chunk = np.pad(mic_chunk, (0, len(lb_chunk) - len(mic_chunk)))
                        mixed = mix_streams(lb_chunk, mic_chunk)
                    else:
                        mixed = lb_chunk
                    self.audio_queue.put((chunk_index, mixed))

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
        """Generic chunking loop for loopback-style streams."""
        chunk_samples = int(CHUNK_DURATION_S * SAMPLE_RATE)
        overlap_samples = int(OVERLAP_DURATION_S * SAMPLE_RATE)
        buffer: list[np.ndarray] = []
        chunk_index = 0

        while not self.stopped():
            try:
                raw = read_fn()
            except Exception:
                break
            audio = np.frombuffer(raw, dtype=np.int16)
            mono = resample(audio, sr, channels)
            buffer.append(mono)

            total = sum(len(b) for b in buffer)
            if total >= chunk_samples:
                chunk = np.concatenate(buffer)[:chunk_samples]
                self.audio_queue.put((chunk_index, chunk))
                chunk_index += 1
                log.debug("Audio chunk %d queued (%d samples)", chunk_index - 1, len(chunk))

                if overlap_samples > 0:
                    leftover = np.concatenate(buffer)[chunk_samples - overlap_samples:]
                    buffer.clear()
                    buffer.append(leftover)
                else:
                    buffer.clear()

        # Flush remaining audio
        if buffer:
            chunk = np.concatenate(buffer)
            if len(chunk) > SAMPLE_RATE:  # Only if > 1 second
                self.audio_queue.put((chunk_index, chunk))
                log.debug("Final audio chunk %d queued (%d samples)", chunk_index, len(chunk))
