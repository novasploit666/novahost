"""Browser launch helper."""

from __future__ import annotations

import os
import sys
import webbrowser


def open_browser(url: str) -> bool:
    """Open the URL using the operating system's default browser."""
    try:
        if sys.platform == "win32":
            startfile = getattr(os, "startfile", None)
            if startfile is not None:
                startfile(url)
                return True
        return bool(webbrowser.open_new_tab(url))
    except (webbrowser.Error, OSError, RuntimeError):
        return False
