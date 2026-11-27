"""The platform's per-user locations for the tool: the state its runs keep apart from any image directory, and the
person's config."""

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


def config_directory() -> Path:
    """Where the person's config for the tool is kept, where tools like VS Code and uv keep theirs."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / DISTRIBUTION
