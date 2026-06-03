"""Entry point for Hearsay: python -m hearsay"""

import multiprocessing
import sys


def main() -> None:
    # RealtimeSTT spawns a child process (spawn start method) for the main
    # transcription model; freeze_support is required for frozen/PyInstaller builds.
    multiprocessing.freeze_support()

    from hearsay.utils.logging_setup import setup_logging

    setup_logging()

    # Must run before any ctranslate2 / faster-whisper import on Windows
    from hearsay.utils.cuda_dlls import register_nvidia_dlls

    register_nvidia_dlls()

    from hearsay.app import HearsayApp

    app = HearsayApp()
    app.run()


if __name__ == "__main__":
    main()
