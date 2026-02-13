# Hearsay

**Windows desktop app that records system audio and/or microphone input and transcribes it in real-time using OpenAI's open-source Whisper model running locally.**

No API calls, no cloud services -- everything runs on your machine.

---

## Features

- **System audio capture** -- record what your speakers play (YouTube, Teams, podcasts, etc.) via WASAPI loopback
- **Microphone capture** -- record from your mic, or mix both sources together
- **Real-time transcription** -- text appears in a live view window as you record
- **Local AI** -- uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2), no internet required after model download
- **GPU + CPU** -- auto-detects NVIDIA GPU; works on CPU with INT8 quantization
- **Markdown output** -- timestamped `.md` transcripts saved to your chosen directory
- **System tray app** -- runs quietly in the tray, right-click to start/stop recording
- **First-run wizard** -- detects hardware, downloads the right model, configures everything
- **Windows installer** -- appears in Add/Remove Programs, Start Menu shortcut, clean uninstall

## Quick Start

### From source

```bash
# Clone the repo
git clone https://github.com/your-org/hearsay.git
cd hearsay

# Install dependencies
pip install -r requirements.txt

# Run
python -m hearsay
```

On first launch, the setup wizard walks you through:
1. Hardware detection (GPU vs CPU)
2. Audio source selection
3. Output directory
4. Model download

After setup, Hearsay lives in your system tray. Right-click the icon to start recording.

### Installed version

Download the latest installer from the [Releases](https://github.com/your-org/hearsay/releases) page and run `HearsaySetup.exe`. The app appears in your Start Menu and Add/Remove Programs.

## Usage

1. **Right-click** the tray icon
2. Choose **Start Recording** > **System Audio**, **Microphone**, or **Both**
3. Audio is transcribed in real-time -- open **Live Transcript** to watch
4. **Stop Recording** when done -- a timestamped `.md` file is saved to your output directory

## Hardware Requirements

| Setup | Recommended Model | Speed |
|-------|-------------------|-------|
| NVIDIA GPU (6+ GB VRAM) | `turbo` (float16) | ~8x real-time |
| NVIDIA GPU (4 GB VRAM) | `small.en` (float16) | ~4x real-time |
| CPU only | `small.en` (int8) | ~1x real-time |

A 1-hour recording transcribes in ~7 min on GPU or ~60 min on CPU.

## Project Structure

```
src/hearsay/
├── __init__.py              # Version string
├── __main__.py              # Entry point
├── app.py                   # Application orchestrator
├── config.py                # AppConfig + ConfigManager (JSON in %APPDATA%)
├── constants.py             # App name, model table, defaults
├── audio/
│   ├── devices.py           # Enumerate loopback + mic devices
│   ├── recorder.py          # AudioRecorder thread
│   ├── mixer.py             # Mix two audio streams
│   └── resampler.py         # Resample to 16kHz mono float32
├── transcription/
│   ├── gpu_detect.py        # Detect CUDA, recommend model
│   ├── model_manager.py     # Download and cache Whisper models
│   ├── engine.py            # TranscriptionEngine (faster-whisper)
│   └── pipeline.py          # TranscriptionPipeline thread
├── output/
│   ├── formatter.py         # Timestamp formatting
│   └── markdown_writer.py   # Write .md transcripts
├── ui/
│   ├── tray.py              # System tray icon (pystray)
│   ├── wizard.py            # First-run setup wizard
│   ├── live_view.py         # Live transcript window
│   ├── settings_window.py   # Settings editor
│   ├── icons.py             # Programmatic icon generation
│   └── theme.py             # customtkinter theme
└── utils/
    ├── paths.py             # %APPDATA%\Hearsay directories
    ├── logging_setup.py     # File + console logging
    └── threading_utils.py   # StoppableThread, safe_after
```

## Building

### PyInstaller (portable)

```bash
build.bat
```

Output in `dist\Hearsay\`.

### Windows Installer

1. Build with PyInstaller first
2. Install [Inno Setup 6+](https://jrsoftware.org/isinfo.php)
3. Compile `installer.iss`

Output: `installer_output\HearsaySetup.exe`

## Tech Stack

- **Python 3.11+**
- **faster-whisper** -- CTranslate2-based Whisper inference
- **PyAudioWPatch** -- WASAPI loopback recording
- **sounddevice** -- Microphone capture
- **customtkinter** -- Modern UI
- **pystray + Pillow** -- System tray
- **PyInstaller + Inno Setup** -- Build and install

## License

MIT
