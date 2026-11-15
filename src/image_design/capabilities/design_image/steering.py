"""Steering an image's agent while it works, from any process, through the messages shared/images/steering.py keeps."""

from pathlib import Path

from image_design.schemas import ImageDesignError, Mark
from image_design.shared.images import marks as marking
from image_design.shared.images import requests
from image_design.shared.images.requests import Reference, invalid
from image_design.shared.images.steering import send
from image_design.shared.images.store import directories, require_image


def steer_image(
    name: str,
    message: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    origin: str | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
) -> None:
    """Leave a message for the image's agent, which the process running it delivers."""
    root, data = directories(directory, data_directory)
    image = require_image(root, data, name)
    run = image.designing()
    if run is None:
        raise ImageDesignError(
            f"No agent is working on {image.name}, so there is none to steer. Start one with design_image, with "
            "resume_session=True to go on in its last session, and the message as its prompt.",
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
        raise invalid("The message is empty. Say what the agent should do.", name)
    marking.require_marks(marks)
    return requests.references(paths)
