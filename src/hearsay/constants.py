"""Application constants and model configuration."""

APP_NAME = "Hearsay"
APP_VERSION = "1.0.3"
APP_AUTHOR = "Hearsay"

# Audio settings
SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # Whisper expects mono
# Variable-length chunking driven by trailing-silence detection.
# A chunk is cut once at least MIN_CHUNK_DURATION_S has accumulated AND the
# trailing SILENCE_DURATION_S of audio is near-silent — or unconditionally once
# MAX_CHUNK_DURATION_S (Whisper's native context window) is reached.
MIN_CHUNK_DURATION_S = 5     # Minimum audio buffered before an early (silence) cut
MAX_CHUNK_DURATION_S = 30    # Hard cap — Whisper's native context window
SILENCE_DURATION_S = 1.0     # Trailing near-silence (seconds) that triggers a cut
SILENCE_RMS_THRESHOLD = 0.01  # RMS on [-1, 1] float audio below which ≈ silence
OVERLAP_DURATION_S = 1       # Overlap between chunks to prevent word splitting
AUDIO_DTYPE = "float32"

# Custom HuggingFace models: short name -> {repo_id, parameters, vram_gb, english_only}
# These models are in Transformers format and must be converted to CTranslate2 on first use.
HF_CUSTOM_MODELS: dict[str, dict] = {
    "small-ko": {
        "repo_id": "SungBeom/whisper-small-ko",
        "parameters": "244M",
        "vram_gb": 2,
        "english_only": False,
    },
    "medium-ko-zeroth": {
        "repo_id": "seastar105/whisper-medium-ko-zeroth",
        "parameters": "769M",
        "vram_gb": 5,
        "english_only": False,
    },
}

# Model table: name -> (parameters, vram_gb, english_only)
MODEL_TABLE = {
    "tiny": ("39M", 1, False),
    "tiny.en": ("39M", 1, True),
    "base": ("74M", 1, False),
    "base.en": ("74M", 1, True),
    "small": ("244M", 2, False),
    "small.en": ("244M", 2, True),
    "medium": ("769M", 5, False),
    "medium.en": ("769M", 5, True),
    "large-v3": ("1550M", 10, False),
    "turbo": ("809M", 6, False),
    # Korean fine-tuned models (HuggingFace, converted to CTranslate2 on first use)
    "small-ko": ("244M", 2, False),
    "medium-ko-zeroth": ("769M", 5, False),
}

# Default model recommendations
DEFAULT_GPU_MODEL = "turbo"
DEFAULT_CPU_MODEL = "small.en"
DEFAULT_GPU_COMPUTE = "float16"
DEFAULT_CPU_COMPUTE = "int8"

# Audio source options
AUDIO_SOURCE_SYSTEM = "system"
AUDIO_SOURCE_MIC = "microphone"
AUDIO_SOURCE_BOTH = "both"

# Tray icon colors (RGB)
ICON_COLOR_IDLE = (100, 100, 100)       # Gray
ICON_COLOR_RECORDING = (220, 50, 50)    # Red
ICON_COLOR_PROCESSING = (50, 150, 220)  # Blue

# Transcript formatting
PARAGRAPH_GAP_S = 2.0  # Silence gap (seconds) that triggers a paragraph break

# UI
LIVE_VIEW_POLL_MS = 250  # Poll transcript queue every 250ms
