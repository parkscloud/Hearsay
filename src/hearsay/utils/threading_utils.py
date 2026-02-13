"""Threading helpers: StoppableThread and safe tkinter scheduling."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)


class StoppableThread(threading.Thread):
    """Thread with a stop event for clean shutdown."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self.daemon = True

    def stop(self) -> None:
        self._stop_event.set()

    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait on the stop event. Returns True if the event was set."""
        return self._stop_event.wait(timeout=timeout)


def safe_after(root: Any, ms: int, func: Callable[..., Any], *args: Any) -> None:
    """Schedule *func* on the tkinter main thread, swallowing errors if root is destroyed."""
    try:
        root.after(ms, func, *args)
    except Exception:
        log.debug("safe_after: root destroyed, skipping callback")
