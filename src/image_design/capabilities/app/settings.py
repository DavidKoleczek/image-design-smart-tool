"""What the app remembers: the person's settings, the same in every directory, and what they picked in each one."""

import os
from pathlib import Path
import sys
from typing import Any

from pydantic import BaseModel, ValidationError

from image_design.core.skill import DISTRIBUTION
from image_design.schemas import AppSettings, AppState, ImageDesignError
from image_design.shared.images.store import make_data_directory, within, write_atomically

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
    """Check `state` and keep it for the images of `data`, replacing what was there but the image shown."""
    checked = _checked(state, AppState, "state", "read_app_state", "bad-state")
    # Set by the server alone, so a view saving what it read earlier does not undo `open_app` bringing an image up.
    checked.shown = read_app_state(data).shown
    return _write_state(checked, data)


def show_image(name: str | None, data: Path) -> None:
    """Keep `name` as the image the app shows, which it opens on; None for none."""
    _write_state(read_app_state(data).model_copy(update={"shown": name}), data)


def follow_move(old: str, new: str, root: Path, data: Path) -> None:
    """Point what the app keeps for `data` at an image, or at everything in a folder, that went from `old` to `new`
    in `root`: the image shown, the tabs, and the pins."""
    state = read_app_state(data)
    shown = None if state.shown is None else _moved_name(state.shown, old, new)
    tabs = [tab.model_copy(update={"name": _moved_name(tab.name, old, new)}) for tab in state.tabs]
    pins = [moved_path(pin, root / old, root / new) for pin in state.pins]
    if shown != state.shown or tabs != state.tabs or pins != state.pins:
        _write_state(state.model_copy(update={"shown": shown, "tabs": tabs, "pins": pins}), data)


def moved_path(path: Path, old: Path, new: Path) -> Path:
    """Where `path` is once `old`, a file or a folder, is at `new`; `path` itself when it is neither `old` nor in
    it."""
    return new / path.relative_to(old) if path.is_relative_to(old) else path


def _moved_name(name: str, old: str, new: str) -> str:
    """Where the image named `name` in the directory is once `old`, an image or a folder, is at `new`."""
    if name.casefold() == old.casefold():
        return new
    return f"{new}{name[len(old) :]}" if within(name, old) else name


def _write_state(checked: AppState, data: Path) -> AppState:
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
