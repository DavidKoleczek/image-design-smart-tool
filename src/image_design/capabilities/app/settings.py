"""What the app remembers: the person's settings, the same in every directory, and what they picked in each one."""

import os
from pathlib import Path
import sys
from typing import Any

from pydantic import BaseModel, ValidationError

from image_design.core.skill import DISTRIBUTION
from image_design.schemas import AppSettings, AppState, ImageDesignError
from image_design.shared.images.store import make_data_directory, write_atomically

SETTINGS = "app-settings.json"
STATE_FOLDER = "app"
STATE = "app.json"


def settings_path() -> Path:
    """The platform's per-user config location for the app's settings, where tools like VS Code and uv keep theirs."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / DISTRIBUTION / SETTINGS


def state_path(data: Path) -> Path:
    """Where the app keeps what was picked for the images of one data directory."""
    return data / STATE_FOLDER / STATE


def read_app_settings(path: Path) -> AppSettings:
    """The settings kept at `path`; the defaults when there are none yet, or they cannot be read."""
    return _read(path, AppSettings)


def save_app_settings(settings: dict[str, Any], path: Path) -> AppSettings:
    """Check `settings` and keep them at `path`, replacing what was there; the last of several apps to save wins."""
    checked = _checked(settings, AppSettings, "setting", "read_app_settings", "bad-settings")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(path, checked.model_dump_json(indent=2))
    except OSError as error:
        raise ImageDesignError(
            f"Could not save the app's settings to {path}: {error}. Check that the folder can be written."
        ) from None
    return checked


def read_app_state(data: Path) -> AppState:
    """What was picked in the app for the images of `data`; the defaults when nothing was, or it cannot be read."""
    return _read(state_path(data), AppState)


def save_app_state(state: dict[str, Any], data: Path) -> AppState:
    """Check `state` and keep it for the images of `data`, replacing what was there."""
    checked = _checked(state, AppState, "state", "read_app_state", "bad-state")
    path = state_path(data)
    try:
        # The data directory's .gitignore leaves this folder out of a project's commits.
        make_data_directory(data)
        path.parent.mkdir(exist_ok=True)
        write_atomically(path, checked.model_dump_json(indent=2))
    except OSError as error:
        raise ImageDesignError(
            f"Could not save the app's state to {path}: {error}. Check that the folder can be written."
        ) from None
    return checked


def _read[Model: BaseModel](path: Path, model: type[Model]) -> Model:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return model()


def _checked[Model: BaseModel](values: dict[str, Any], model: type[Model], what: str, reader: str, reason: str) -> Model:
    try:
        return model.model_validate(values)
    except ValidationError as error:
        problem = error.errors()[0]
        field = ".".join(str(part) for part in problem["loc"]) or what
        raise ImageDesignError(
            f"The app {what} {field} is not valid: {problem['msg']}. Send what `{reader}` returns, changed only where "
            "the person changed it.",
            reason,
        ) from None
