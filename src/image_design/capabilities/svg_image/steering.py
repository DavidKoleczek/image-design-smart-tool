"""Steering a drawing while its agent works, from any process, through the messages shared/images/steering.py keeps."""

from pathlib import Path

from image_design.schemas import SVG_SUFFIX, ImageDesignError, Mark
from image_design.shared.images import marks as marking
from image_design.shared.images import requests
from image_design.shared.images.requests import Reference, invalid
from image_design.shared.images.steering import send
from image_design.shared.images.store import directories, require_image


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
