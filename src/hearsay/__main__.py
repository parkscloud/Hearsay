"""Entry point for Hearsay: python -m hearsay"""

import sys


def main() -> None:
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
