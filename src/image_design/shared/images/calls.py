"""Image calls an image's agent makes: which agent's run made each, so the agent's conversation has them."""

import os
from pathlib import Path
from typing import NamedTuple

from image_design.schemas import CHATGPT_IMAGE_MODEL, ImageDesignError, ImageRunRecord
from image_design.shared.images.store import StoredImage, find_design, image_by_id

# Names the agent's run to the processes it starts, so each call made from them is that run's, whatever surface made
# it: the CLI, or a script of the agent's that calls the library.
PARENT = "IMAGE_DESIGN_PARENT"


class Parent(NamedTuple):
    """The agent's run a call names as its parent, and the image that run is kept with."""

    image: StoredImage
    run: ImageRunRecord


def parent_of(root: Path, data: Path, parent: str | None, name: str) -> Parent | None:
    """The agent's run that makes a call: the one named, else the one this process was started by, else None."""
    parent = parent or os.environ.get(PARENT) or None
    if parent is None:
        return None
    found = find_design(root, data, parent)
    if found is None:
        raise ImageDesignError(
            f"There is no agent's run {parent!r} in {data} to make the call on {name} for. Pass the --directory and "
            f"--data-directory that run is kept in, or unset {PARENT} to make the call on its own.",
            "no-such-run",
            name,
        )
    return Parent(*found)


def given(parent: Parent | None) -> str | None:
    """What the agent's run that makes a call was given to make its images with: an OpenAI image model's ID, or
    `chatgpt`; None for a call made on its own."""
    image_model = parent.run.request.get("image_model") if parent is not None else None
    return image_model if isinstance(image_model, str) else None


def require_given(parent: Parent | None, image_model: str, name: str) -> None:
    """Raise for a call to another image model than its agent was given, before anything is sent."""
    picked = given(parent)
    if picked is None or picked == image_model:
        return
    use = "generate-chatgpt-image" if picked == CHATGPT_IMAGE_MODEL else f"generate-openai-image with --model {picked}"
    raise ImageDesignError(
        f"This agent was given {picked} to make its images with, not {image_model}. Make the call with {use}.",
        "invalid-request",
        name,
    )


def record(run: ImageRunRecord, parent: Parent | None, image: StoredImage) -> None:
    """Note on the run the agent's run that made it, and link it to that agent's image when that is another one, so
    the agent's conversation has it."""
    if parent is None:
        return
    run.parent, run.parent_image = parent.run.id, parent.image.record.id
    if run.parent_image == image.record.id:
        return
    keeper = image_by_id(image.root, image.data, run.parent_image)
    if keeper is not None:
        keeper.link(image.record.id, run.id)
