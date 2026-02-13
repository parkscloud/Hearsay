"""Entry point for Hearsay: python -m hearsay"""

import sys


def main() -> None:
    from hearsay.utils.logging_setup import setup_logging

    setup_logging()

    from hearsay.app import HearsayApp

    app = HearsayApp()
    app.run()


if __name__ == "__main__":
    main()
