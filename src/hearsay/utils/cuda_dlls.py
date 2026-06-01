"""Register NVIDIA pip-package DLL directories on Windows before ctranslate2 loads."""

from __future__ import annotations

import logging
import os
import site
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _nvidia_bin_dirs() -> list[Path]:
    """Yield every nvidia/<pkg>/bin directory found in any site-packages."""
    search_roots: list[Path] = []

    # user site-packages (pip install --user)
    try:
        user_site = site.getusersitepackages()
        if user_site:
            search_roots.append(Path(user_site))
    except Exception:
        pass

    # system / venv site-packages
    for p in site.getsitepackages():
        search_roots.append(Path(p))

    found: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        nvidia_root = root / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for bin_dir in nvidia_root.glob("*/bin"):
            if bin_dir.is_dir() and bin_dir not in seen:
                seen.add(bin_dir)
                found.append(bin_dir)

    return found


def register_nvidia_dlls() -> bool:
    """Add NVIDIA pip-package bin dirs to the Windows DLL search path.

    Returns True if at least one directory was registered.
    No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return False

    dirs = _nvidia_bin_dirs()
    if not dirs:
        log.debug("No nvidia pip-package bin dirs found; skipping DLL registration")
        return False

    registered = 0
    for d in dirs:
        try:
            os.add_dll_directory(str(d))
            log.debug("Registered DLL dir: %s", d)
            registered += 1
        except Exception as exc:
            log.warning("Could not register DLL dir %s: %s", d, exc)

    if registered:
        log.info("Registered %d NVIDIA DLL director%s from pip packages",
                 registered, "y" if registered == 1 else "ies")
    return registered > 0
