# Local Speech-to-Text on Windows: Comprehensive Research Summary
## February 2026

---

## 1. Recording System/Computer Audio on Windows

The goal here is to capture audio that is playing *out of your speakers* (YouTube, Teams meetings, media players, etc.) rather than microphone input.

### 1.1 WASAPI Loopback (Recommended - Built into Windows)

**What it is:** Windows Audio Session API (WASAPI) is a low-level Windows audio API. Its "loopback" mode captures the audio stream being sent to an output device (speakers/headphones) *digitally*, before it reaches the DAC. This means perfect quality -- no analog round-trip.

**Key facts:**
- Built into Windows 10/11 -- no extra drivers or software required.
- Works regardless of whether your sound card has a "Stereo Mix" device.
- Captures the mixed output of everything playing through the selected audio endpoint.
- Since Windows 10 version 1703, event-driven loopback clients are fully supported.
- Since Windows 10 version 2004, you can capture audio from a *specific process* (and its children) rather than the entire system mix, using `ActivateAudioInterfaceAsync` with the new initialization structure.

**How to use it (easiest path -- Audacity):**
1. Open Audacity.
2. In the Audio Setup toolbar, set Host to **"Windows WASAPI"**.
3. For Recording Device, select your output device with **(loopback)** appended, e.g., `Speakers (Realtek High Definition Audio) (loopback)`.
4. Disable "Enable audible input monitoring" under Transport > Transport Options.
5. Start the audio source (YouTube, Teams, etc.), then press Record in Audacity.
6. Export as WAV or MP3 when done.

**Important:** WASAPI loopback needs an active audio stream to capture -- start your audio *before* pressing record.

### 1.2 Virtual Audio Cables

**VB-Audio Virtual Cable (VB-CABLE):**
- Free donationware from [vb-audio.com](https://vb-audio.com/Cable/).
- Installs a virtual playback device ("CABLE Input") and a virtual recording device ("CABLE Output").
- Any audio sent to CABLE Input appears on CABLE Output.
- Supports all sample rates from 8 kHz to 192 kHz, all Windows audio interfaces (MME, DirectShow, WDM, KS, WASAPI).
- **Use case:** Set your system default playback device to "CABLE Input," then record from "CABLE Output" in any recording app. Useful when an application does not respect the system default device, or when you need to route audio between specific applications.
- **Downside:** You won't hear the audio through your speakers unless you also set up monitoring (VoiceMeeter can help).

**VoiceMeeter (also from VB-Audio):**
- Free virtual audio mixer that provides more sophisticated routing.
- Can split audio so you both hear it *and* record it simultaneously.
- VoiceMeeter Banana and VoiceMeeter Potato offer more virtual inputs/outputs.

### 1.3 FFmpeg (Command Line)

FFmpeg can record audio on Windows using DirectShow (`-f dshow`):

```bash
# List available audio devices
ffmpeg -list_devices true -f dshow -i dummy

# Record from a specific device (e.g., Stereo Mix or a Virtual Cable output)
ffmpeg -f dshow -i audio="Stereo Mix (Realtek High Definition Audio)" -t 300 output.wav

# Record from virtual cable output
ffmpeg -f dshow -i audio="CABLE Output (VB-Audio Virtual Cable)" output.wav
```

**Note:** FFmpeg's dshow backend does not natively support WASAPI loopback. You need either Stereo Mix enabled or a virtual cable to present system audio as a recordable device to FFmpeg. You can also pipe WASAPI loopback output into FFmpeg:

```bash
wasapi_capture.exe 2>nul | ffmpeg -f s16le -ar 48000 -ac 2 -i pipe:0 output.mp3
```

### 1.4 OBS Studio

- Free, open-source, supports "Audio Output Capture" source which captures system/desktop audio directly.
- Can record just the audio track (no video) or audio+video.
- Uses WASAPI internally on Windows.
- Good option if you also want screen recording.

### 1.5 Summary Table: System Audio Capture Methods

| Method | Ease of Use | Quality | Requires Install | Hear Audio While Recording |
|--------|-------------|---------|------------------|---------------------------|
| Audacity + WASAPI Loopback | Easy | Perfect (digital) | Audacity only | Yes |
| VB-CABLE + any recorder | Moderate | Perfect (digital) | VB-CABLE driver | Need monitoring setup |
| FFmpeg + Stereo Mix | CLI-only | Perfect (digital) | FFmpeg, Stereo Mix enabled | Yes |
| OBS Audio Output Capture | Easy | Perfect (digital) | OBS | Yes |
| Python (PyAudioWPatch) | Developer | Perfect (digital) | Python packages | Configurable |

---

## 2. Local Speech-to-Text Models and Tools

### 2.1 OpenAI Whisper (Open Source, Runs Locally)

**What it is:** Whisper is an open-source automatic speech recognition (ASR) model released by OpenAI in September 2022, with updates through 2024. It was trained on 680,000 hours of multilingual audio. It runs entirely locally -- no API calls, no internet connection required after downloading the model.

**Installation:**
```bash
# Install via pip
pip install -U openai-whisper

# OR install the latest from GitHub
pip install git+https://github.com/openai/whisper.git
```

**System dependency -- FFmpeg is required:**
```bash
# Windows (via Chocolatey)
choco install ffmpeg

# Windows (via Scoop)
scoop install ffmpeg
```

**Python dependency:** Requires Python 3.8-3.11 and PyTorch.

**Command-line usage:**
```bash
# Basic transcription with the turbo model
whisper audio.wav --model turbo

# Specify language
whisper meeting.wav --model medium --language English

# Translate non-English to English
whisper japanese.wav --model medium --language Japanese --task translate

# Output as specific format
whisper audio.wav --model turbo --output_format txt
```

**Python usage:**
```python
import whisper

model = whisper.load_model("turbo")
result = model.transcribe("audio.wav")
print(result["text"])
```

**Output formats:** txt, vtt (WebVTT subtitles), srt (SubRip subtitles), tsv, json.

#### Whisper Model Table

| Size | Parameters | English-only Model | Multilingual Model | Required VRAM | Relative Speed |
|------|-----------|-------------------|-------------------|---------------|----------------|
| tiny | 39 M | `tiny.en` | `tiny` | ~1 GB | ~10x |
| base | 74 M | `base.en` | `base` | ~1 GB | ~7x |
| small | 244 M | `small.en` | `small` | ~2 GB | ~4x |
| medium | 769 M | `medium.en` | `medium` | ~5 GB | ~2x |
| large | 1,550 M | N/A | `large` | ~10 GB | 1x |
| large-v2 | 1,550 M | N/A | `large-v2` | ~10 GB | 1x |
| large-v3 | 1,550 M | N/A | `large-v3` | ~10 GB | 1x |
| turbo | 809 M | N/A | `turbo` | ~6 GB | ~8x |

**Speed notes:** Relative speeds measured on an NVIDIA A100. The turbo model is a pruned version of large-v3 with decoder layers reduced from 32 to 4, achieving near-large-v3 accuracy at near-base-model speed.

**Accuracy (English Word Error Rate -- WER):**
- `large-v3`: ~7.4% WER on standard benchmarks
- `turbo`: ~7.75% WER (within 1-2% of large-v3)
- `medium`: ~8-10% WER
- `small`: ~10-12% WER
- `tiny`: ~15-18% WER
- On clean speech (LibriSpeech clean), large models achieve ~2% WER.

**The `.en` models** (English-only) perform better than their multilingual counterparts for English, especially at smaller sizes (`tiny.en` and `base.en`).

### 2.2 faster-whisper

**What it is:** A reimplementation of Whisper using [CTranslate2](https://github.com/OpenNMT/CTranslate2), a fast inference engine for Transformer models. It is the most popular Whisper variant for Python users.

**Key advantages over original Whisper:**
- **Up to 4x faster** transcription.
- **Lower memory usage** (e.g., large-v2 on GPU: 4525 MB vs. 4708 MB for original).
- **int8 quantization** support -- up to 40% memory savings with minimal accuracy loss.
- **Does NOT require FFmpeg** (uses PyAV internally for audio decoding).
- Native **word-level timestamps**.
- **Batched inference** for higher throughput.
- Supports **VAD (Voice Activity Detection)** filtering via Silero VAD.

**Installation:**
```bash
pip install faster-whisper
```

**GPU requirements (NVIDIA):** cuBLAS and cuDNN 9 for CUDA 12.

**Python usage:**
```python
from faster_whisper import WhisperModel

# GPU with float16
model = WhisperModel("large-v3", device="cuda", compute_type="float16")

# CPU with int8 (fast, low memory)
model = WhisperModel("large-v3", device="cpu", compute_type="int8")

segments, info = model.transcribe("audio.mp3", beam_size=5)

print(f"Detected language: {info.language} (probability {info.language_probability:.2f})")

for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
```

**Performance comparison (large-v2 model):**

| Implementation | GPU (RTX 3070 Ti) | CPU (i7-12700K) |
|---------------|-------------------|-----------------|
| openai/whisper | 2m23s, 4708 MB | 6m58s (fp32) |
| faster-whisper | 1m03s, 4525 MB | 2m37s (fp32), 1m42s (int8) |

### 2.3 whisper.cpp

**What it is:** A C/C++ port of Whisper using the [ggml](https://github.com/ggerganov/ggml) tensor library. No Python runtime or PyTorch needed.

**Key advantages:**
- **Pure C/C++** -- minimal dependencies, small binary.
- Excellent on **CPU** -- uses optimized SIMD instructions (AVX2, NEON, etc.).
- Optional **CUDA, Metal, OpenCL** acceleration.
- **Quantized models** (Q4, Q5, Q8) for dramatically lower memory usage.
- Ideal for edge/embedded devices or environments where Python/PyTorch are not desirable.
- Deterministic builds, no Python overhead.

**Installation on Windows:**
```bash
# Clone the repo
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp

# Build with CMake
cmake -B build
cmake --build build -j --config Release

# With CUDA support (requires NVIDIA CUDA Toolkit 12.x)
cmake -B build -DGGML_CUDA=1
cmake --build build -j --config Release
```

Or download pre-built binaries from the [GitHub Releases](https://github.com/ggml-org/whisper.cpp/releases).

**Models:** Download GGML-format models from https://huggingface.co/ggerganov/whisper.cpp

**Usage:**
```bash
# Download a model
./models/download-ggml-model.sh base.en

# Transcribe
./build/bin/whisper-cli -m models/ggml-base.en.bin -f samples/jfk.wav
```

**Limitations vs. faster-whisper:**
- Word-level timestamps can drift by 300-800ms on complex speech.
- Less Python-ecosystem integration (though Python bindings exist).

### 2.4 Other Notable Local STT Tools

**Vosk:**
- Lightweight offline speech recognition, supports 20+ languages.
- Models are very small: ~50 MB per language (vs. gigabytes for Whisper).
- Excellent for real-time/streaming use cases, mobile, and embedded devices.
- Lower accuracy than Whisper, but dramatically more resource-efficient.
- Python API: `pip install vosk`
- Best for: resource-constrained environments, real-time streaming, keyword spotting.

**NVIDIA Parakeet TDT 1.1B:**
- English-only model with ~8% WER but >2,000x real-time factor (extremely fast).
- Requires NVIDIA GPU.
- Part of NVIDIA NeMo toolkit.

**Distil-Whisper:**
- Knowledge-distilled version of Whisper large-v3.
- 756M parameters, 6x faster than Whisper V3.
- Nearly identical accuracy to the full model.
- `pip install transformers` (via Hugging Face).

**Moonshine (by Useful Sensors):**
- Only 27M parameters -- designed for mobile/embedded.
- Good for edge deployment where resources are very limited.

### 2.5 Hardware Requirements Summary

| Scenario | Recommended Hardware | Model to Use |
|----------|---------------------|-------------|
| Budget / No GPU | Any modern CPU, 8 GB RAM | tiny.en or base.en (Whisper), or Vosk |
| Mid-range GPU (4-6 GB VRAM) | GTX 1660 / RTX 3060 | small, medium, or turbo (with faster-whisper int8) |
| Good GPU (8+ GB VRAM) | RTX 3070/3080/4070+ | large-v3 or turbo (faster-whisper float16) |
| CPU-only, need quality | Modern 8+ core CPU, 16 GB RAM | large-v3 with faster-whisper int8 (slow but works) |
| Edge / embedded | ARM / low-power | whisper.cpp with tiny/base quantized, or Moonshine |

**Practical guidance:**
- The **turbo** model is the best all-around choice for most users: near-large-v3 accuracy at ~8x the speed, needing only ~6 GB VRAM.
- **faster-whisper with int8 quantization** on CPU is surprisingly usable -- transcribing a 13-minute audio file in under 2 minutes on a modern i7.
- If you have no GPU and need speed, **whisper.cpp** with a quantized model is the most efficient CPU option.

---

## 3. End-to-End Workflow

### Workflow A: Simple (GUI-based)

1. **Record** system audio with **Audacity** (WASAPI loopback).
2. **Export** to WAV (File > Export Audio > WAV).
3. **Transcribe** with Whisper CLI:
   ```bash
   whisper meeting-recording.wav --model turbo --output_format txt
   ```
4. Open the resulting `.txt` file.

### Workflow B: Command-Line (FFmpeg + faster-whisper)

```bash
# Step 1: Record system audio via virtual cable (e.g., 5 minutes)
ffmpeg -f dshow -i audio="CABLE Output (VB-Audio Virtual Cable)" -t 300 -ar 16000 -ac 1 recording.wav

# Step 2: Transcribe
python -c "
from faster_whisper import WhisperModel
model = WhisperModel('turbo', device='cuda', compute_type='float16')
segments, info = model.transcribe('recording.wav', beam_size=5)
with open('transcript.md', 'w', encoding='utf-8') as f:
    f.write('# Meeting Transcript\n\n')
    for seg in segments:
        timestamp = f'[{int(seg.start//60):02d}:{seg.start%60:05.2f}]'
        f.write(f'{timestamp} {seg.text.strip()}\n\n')
print('Transcript saved to transcript.md')
"
```

### Workflow C: All-in-One Python Script

```python
"""
End-to-end: Record system audio -> Transcribe with faster-whisper -> Save markdown
Requires: pip install PyAudioWPatch faster-whisper
"""
import pyaudiowpatch as pyaudio
import wave
import time
from faster_whisper import WhisperModel

# --- STEP 1: Record system audio via WASAPI loopback ---
DURATION = 300  # seconds
OUTPUT_WAV = "recording.wav"

p = pyaudio.PyAudio()

# Get the default WASAPI loopback device
wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
loopback = p.get_wasapi_loopback_analogue_by_dict(default_speakers)

print(f"Recording from: {loopback['name']}")
print(f"Sample rate: {int(loopback['defaultSampleRate'])}")
print(f"Channels: {loopback['maxInputChannels']}")

stream = p.open(
    format=pyaudio.paInt16,
    channels=loopback["maxInputChannels"],
    rate=int(loopback["defaultSampleRate"]),
    input=True,
    input_device_index=loopback["index"],
    frames_per_buffer=1024,
)

frames = []
print(f"Recording for {DURATION} seconds... Press Ctrl+C to stop early.")
try:
    for _ in range(0, int(loopback["defaultSampleRate"] / 1024 * DURATION)):
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(data)
except KeyboardInterrupt:
    print("Recording stopped early.")

stream.stop_stream()
stream.close()
p.terminate()

# Save to WAV
wf = wave.open(OUTPUT_WAV, "wb")
wf.setnchannels(loopback["maxInputChannels"])
wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
wf.setframerate(int(loopback["defaultSampleRate"]))
wf.writeframes(b"".join(frames))
wf.close()
print(f"Saved recording to {OUTPUT_WAV}")

# --- STEP 2: Transcribe with faster-whisper ---
print("Loading Whisper model...")
model = WhisperModel("turbo", device="cuda", compute_type="float16")
# For CPU: model = WhisperModel("turbo", device="cpu", compute_type="int8")

print("Transcribing...")
segments, info = model.transcribe(OUTPUT_WAV, beam_size=5, word_timestamps=True)

# --- STEP 3: Write markdown transcript ---
with open("transcript.md", "w", encoding="utf-8") as f:
    f.write("# Transcript\n\n")
    f.write(f"**Language:** {info.language} (confidence: {info.language_probability:.1%})\n\n")
    f.write("---\n\n")
    for segment in segments:
        start_min = int(segment.start // 60)
        start_sec = segment.start % 60
        f.write(f"**[{start_min:02d}:{start_sec:05.2f}]** {segment.text.strip()}\n\n")

print("Transcript saved to transcript.md")
```

### Workflow D: Use a Desktop App

Several GUI applications wrap Whisper for a no-code experience:

- **Whispering** -- Open-source desktop app (Windows download available). Push-to-talk dictation, works with local models or fully offline.
- **WizWhisp** -- Available on the Microsoft Store, powered by Whisper, fully offline.
- **WhisperDesktop** -- A lightweight Windows GUI for whisper.cpp.
- **Whishper** -- Self-hosted web UI using faster-whisper as the backend; run via Docker.

---

## 4. Python Ecosystem

### 4.1 Core Packages

| Package | Purpose | Install |
|---------|---------|---------|
| `openai-whisper` | Official Whisper (PyTorch-based) | `pip install openai-whisper` |
| `faster-whisper` | CTranslate2-based Whisper (recommended) | `pip install faster-whisper` |
| `whisper-live` | Real-time streaming transcription | `pip install whisper-live` |
| `insanely-fast-whisper` | HuggingFace pipeline-based Whisper | `pip install insanely-fast-whisper` |
| `transcribe-anything` | CLI tool wrapping faster-whisper | `pip install transcribe-anything` |
| `vosk` | Lightweight offline STT | `pip install vosk` |

### 4.2 Audio Recording/Handling Packages

| Package | Purpose | Install | Notes |
|---------|---------|---------|-------|
| `PyAudioWPatch` | Record from speakers via WASAPI loopback | `pip install PyAudioWPatch` | **The key package for recording system audio in Python on Windows** |
| `pyaudio` | Standard PortAudio bindings | `pip install pyaudio` | Does NOT support WASAPI loopback natively |
| `sounddevice` | PortAudio wrapper (nicer API) | `pip install sounddevice` | No built-in loopback support |
| `pydub` | Audio manipulation (convert, slice, etc.) | `pip install pydub` | Needs FFmpeg for non-WAV formats |
| `librosa` | Audio analysis | `pip install librosa` | Good for pre-processing |
| `PyAV` | FFmpeg Python bindings | `pip install av` | Used internally by faster-whisper |

### 4.3 Key Notes for Python Developers

**PyAudioWPatch is essential for WASAPI loopback in Python:**
- It is a fork of PyAudio with a patched PortAudio that adds WASAPI loopback support.
- Provides helper methods: `get_default_wasapi_loopback()`, `get_wasapi_loopback_analogue_by_dict()`.
- The standard `pyaudio` and `sounddevice` packages do NOT support loopback recording.

**faster-whisper vs. openai-whisper for Python projects:**
- `faster-whisper` is strictly better for inference: faster, lower memory, no FFmpeg dependency.
- `openai-whisper` is useful if you need to fine-tune the model or need exact compatibility with the original paper.
- Both accept the same audio formats and produce equivalent output quality.

**Recommended minimal Python setup:**
```bash
pip install PyAudioWPatch faster-whisper
```

This gives you everything needed: WASAPI loopback recording + fast local transcription.

---

## 5. Practical Recommendations

### For Most Users: "Just Works" Setup

1. Install **Audacity** (free) for recording system audio via WASAPI loopback.
2. Install **Python 3.10+** and run `pip install faster-whisper`.
3. Use the **turbo** model for the best speed/accuracy tradeoff.
4. Transcribe: `python -c "from faster_whisper import WhisperModel; m = WhisperModel('turbo'); segs, _ = m.transcribe('audio.wav'); [print(s.text) for s in segs]"`

### For Developers: Automated Pipeline

1. Use **PyAudioWPatch** for programmatic system audio capture.
2. Use **faster-whisper** with `device="cuda"` if you have a GPU, or `device="cpu", compute_type="int8"` otherwise.
3. The turbo model + faster-whisper + int8 quantization works well even on CPU-only machines.

### For Maximum Accuracy

- Use `large-v3` model with `faster-whisper` on a GPU with 10+ GB VRAM.
- Enable `word_timestamps=True` and `vad_filter=True` for cleaner output.
- Pre-process audio to 16 kHz mono WAV for best results.

### For Maximum Speed (CPU-only)

- Use `whisper.cpp` with a quantized `base.en` or `small.en` model.
- Or `faster-whisper` with `tiny.en` or `base.en` and `compute_type="int8"`.

---

## Sources

- [OpenAI Whisper GitHub](https://github.com/openai/whisper)
- [faster-whisper GitHub (SYSTRAN)](https://github.com/SYSTRAN/faster-whisper)
- [whisper.cpp GitHub (ggml-org)](https://github.com/ggml-org/whisper.cpp)
- [PyAudioWPatch GitHub](https://github.com/s0d3s/PyAudioWPatch)
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)
- [Microsoft WASAPI Loopback Documentation](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)
- [Audacity WASAPI Recording Tutorial](https://manual.audacityteam.org/man/tutorial_recording_computer_playback_on_windows.html)
- [Northflank Open Source STT Benchmarks 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Modal: Top Open Source STT Models 2025](https://modal.com/blog/open-source-stt)
- [Tom's Hardware: Whisper GPU Benchmarks](https://www.tomshardware.com/news/whisper-audio-transcription-gpus-benchmarked)
- [Vosk Speech Recognition Guide](https://www.videosdk.live/developer-hub/stt/vosk-speech-recognition)
- [FFmpeg System Audio Recording on Windows](https://www.addictivetips.com/windows-tips/record-system-sound-with-ffmpeg-on-windows-10/)
