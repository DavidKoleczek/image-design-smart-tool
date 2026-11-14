"""Steering a drawing while its agent works, from any process: each message is a folder in its run's folder.

The process running the drawing looks for new ones as it looks for a cancel, delivers each to the agent, and moves it
to the run's delivered messages.
"""

from datetime import UTC, datetime
from pathlib import Path
import secrets

from pydantic import BaseModel, Field

from image_design.schemas import SVG_SUFFIX, ImageDesignError, Mark
from image_design.shared.images import marks as marking
from image_design.shared.images import requests
from image_design.shared.images.requests import Reference, invalid, write_references
from image_design.shared.images.store import directories, require_image

STEER = "steer"
STEERED = "steered"
MESSAGE = "steering.json"


class Steering(BaseModel):
    """One message for the agent, as its folder keeps it."""

    message: str
    origin: str | None = None
    references: list[str] = Field(default_factory=list, description="Files in the message's folder")
    marks: list[Mark] = Field(default_factory=list)


def steer_svg_image(
    name: str,
    message: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    origin: str | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
) -> None:
    """Leave a message for the agent drawing the image, which the process running it delivers."""
    root, data = directories(directory, data_directory)
    image = require_image(root, data, name)
    run = image.running()
    if run is None or run.method != "svg":
        raise ImageDesignError(
            f"Image {image.name} has no drawing going, so there is no agent to steer. Start a new run with "
            "resume_session=True and the message as its prompt.",
            "not-running",
            image.name,
        )
    send(
        image.run_folder(run.id),
        message,
        origin,
        prepared(message, references or [], marks or [], image.name),
        marks or [],
    )


def prepared(message: str, paths: list[Path], marks: list[Mark], name: str) -> list[Reference]:
    """The references of a steering message converted for showing, once the message is known to be one to send."""
    if not message.strip():
        raise invalid("The message is empty. Say what the agent should change.", name)
    if Path(name).suffix.lower() != SVG_SUFFIX:
        raise invalid(f"Image {name} is not an SVG, and only a drawing takes steering.", name)
    marking.require_marks(marks)
    return requests.references(paths)


def send(run_folder: Path, message: str, origin: str | None, sent: list[Reference], marks: list[Mark]) -> None:
    """Leave the message in the run's folder, written aside and renamed so the run never reads half of one."""
    folder = run_folder / STEER
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now(UTC):%Y%m%d-%H%M%S-%f}-{secrets.token_hex(3)}"
    partial = folder / f".{name}.tmp"
    partial.mkdir()
    files = write_references(sent, partial)
    steering = Steering(message=message, origin=origin, references=[file.name for file in files], marks=marks)
    (partial / MESSAGE).write_text(steering.model_dump_json(indent=2), encoding="utf-8")
    partial.rename(folder / name)


def pending(run_folder: Path) -> list[Path]:
    """The folders of the messages not yet delivered, oldest first."""
    folder = run_folder / STEER
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.is_dir() and not path.name.startswith("."))


def read(message: Path) -> Steering:
    return Steering.model_validate_json((message / MESSAGE).read_text(encoding="utf-8"))


def delivered(message: Path, run_folder: Path) -> Path:
    """Move a delivered message to the run's delivered messages, where its files stay for the agent, and return it."""
    target = run_folder / STEERED / message.name
    target.parent.mkdir(parents=True, exist_ok=True)
    message.rename(target)
    return target
