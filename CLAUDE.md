# CLAUDE.md

Project guide for AI-assisted development sessions. This file is the durable, portable project memory — update it when workflows or architecture change. **This repo is public: never put personal information, machine-specific paths, or incident details in this file or any committed file.**

Hearsay is a Windows tray app: WASAPI loopback + microphone capture → faster-whisper (fully local) → timestamped markdown transcripts.

## Build & release

**Build the installer after every code change.** From the project root (~2 minutes total):

1. `pyinstaller --noconfirm Hearsay.spec` → `dist\Hearsay\` (`build.bat` wraps this; the spec is the canonical build definition)
2. `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss` → `installer_output\HearsaySetup.exe`

The version lives in **three** files that must stay in sync: `src/hearsay/__init__.py` (`__version__`), `src/hearsay/constants.py` (`APP_VERSION`), `installer.iss` (`AppVersion`). GitHub release flow is in `RELEASING.md`.

Run from source: `python -m hearsay` with `src` on `PYTHONPATH`.

## Conventions

- Issue/incident write-ups (`ISSUE_*.md`) are local working notes — never commit them (gitignored). Durable resolutions belong in release notes and commit messages.
- Stage files explicitly when committing; avoid `git add -A`.
- No test suite exists. Verify changes with throwaway harnesses: a stub-engine script for pipeline/writer logic (fake `engine.transcribe` returning canned segments), and a real-device script that instantiates `AudioRecorder` + pipeline directly while driving Windows TTS (`System.Speech`) through the speakers so the loopback stream has real speech.

## Architecture (the non-obvious parts)

- **Threading:** background threads subclass `StoppableThread` (`utils/threading_utils.py`); UI updates from threads go through `safe_after(root, ms, callback)`.
- **Audio flow:** `AudioRecorder` uses callback-driven capture (never blocking reads — stop must stay <1s) and cuts wall-clock ~30s windows from per-source buffers that keep a 1s overlap tail. It queues `AudioChunk(index, window_start, parts: {source → ndarray})`, system-first.
- **Pipeline:** transcribes each source in a window separately (no mixing), applies per-source overlap dedup, then a fuzzy echo guard — a mic segment whose words ≥80% match the same window's system text (in order, `difflib`) is dropped as speaker echo. Emits one merged, source-tagged `TranscriptionResult` (`segments` carry `source`; `window_start` is wall-clock seconds).
- **Writer:** `MarkdownWriter` inserts `**Remote [m:ss]:**` / `**Local [m:ss]:**` labels on every source switch (single-source sessions naturally get one label at the top); within a source, a ≥2s gap starts a new paragraph. `post_process()` cleans text per label-block so labels survive the filler/duplicate/whitespace passes. Empty sessions write "No speech was captured during this session."
- **Session lifecycle:** fresh queues per session (no cross-session bleed); teardown waits for the recorder thread to actually exit before the next session may start; device opens retry 5× with backoff; recorder death surfaces via `on_fatal` → tray notification + session stop, backed by a 5s `is_alive()` watchdog.
- **Audio is never persisted to disk** (by design) — a failed transcription is unrecoverable, which is why recording failures must be loud.
- Config and logs live under `%APPDATA%\Hearsay\`; Whisper models are cached there too.
