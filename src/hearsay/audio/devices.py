"""Enumerate loopback (system audio) and microphone devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Represents an audio device."""

    index: int
    name: str
    channels: int
    sample_rate: int
    is_loopback: bool


def list_loopback_devices() -> list[AudioDevice]:
    """Return WASAPI loopback devices (system audio capture)."""
    import pyaudiowpatch as pyaudio

    devices: list[AudioDevice] = []
    p = pyaudio.PyAudio()
    try:
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev.get("isLoopbackDevice"):
                devices.append(AudioDevice(
                    index=dev["index"],
                    name=dev["name"],
                    channels=dev["maxInputChannels"],
                    sample_rate=int(dev["defaultSampleRate"]),
                    is_loopback=True,
                ))
    finally:
        p.terminate()
    log.debug("Found %d loopback devices", len(devices))
    return devices


def get_default_loopback() -> AudioDevice | None:
    """Return the default loopback device (speakers)."""
    import pyaudiowpatch as pyaudio

    p = pyaudio.PyAudio()
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if (
                dev.get("isLoopbackDevice")
                and dev["name"].startswith(default_speakers["name"])
            ):
                return AudioDevice(
                    index=dev["index"],
                    name=dev["name"],
                    channels=dev["maxInputChannels"],
                    sample_rate=int(dev["defaultSampleRate"]),
                    is_loopback=True,
                )
    except Exception:
        log.warning("Could not find default loopback device", exc_info=True)
    finally:
        p.terminate()
    return None


def list_microphone_devices() -> list[AudioDevice]:
    """Return available microphone input devices."""
    import sounddevice as sd

    devices: list[AudioDevice] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and dev["hostapi"] == 0:
            devices.append(AudioDevice(
                index=i,
                name=dev["name"],
                channels=dev["max_input_channels"],
                sample_rate=int(dev["default_samplerate"]),
                is_loopback=False,
            ))
    log.debug("Found %d microphone devices", len(devices))
    return devices


def get_default_microphone() -> AudioDevice | None:
    """Return the default microphone device."""
    import sounddevice as sd

    try:
        default = sd.query_devices(kind="input")
        idx = sd.default.device[0]
        return AudioDevice(
            index=idx,
            name=default["name"],
            channels=default["max_input_channels"],
            sample_rate=int(default["default_samplerate"]),
            is_loopback=False,
        )
    except Exception:
        log.warning("Could not find default microphone", exc_info=True)
    return None
