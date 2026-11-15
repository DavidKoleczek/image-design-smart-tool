"""The platform's per-user state location for the tool: what its runs keep apart from any image directory."""

import os
from pathlib import Path
import sys

from image_design.core.skill import DISTRIBUTION


def state_directory() -> Path:
    """Where the tool keeps state for this user, such as what an agent's later run resumes."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / DISTRIBUTION
