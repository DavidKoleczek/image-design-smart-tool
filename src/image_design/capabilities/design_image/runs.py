"""A run of an image's agent: an image run kept in designs.json, which has the agent's session and takes steering."""

import asyncio
from pathlib import Path
from typing import Protocol

from image_design.capabilities.design_image import steering
from image_design.schemas import ImageDesignError, ImageRunRecord, Mark
from image_design.shared.images.runs import DetachedRun, ImageRun, InProcessRun
from image_design.shared.images.steering import send
from image_design.shared.images.store import load_designs


class DesignRun(ImageRun, Protocol):
    """An image's agent at work: an image run, the agent's session, and a way to steer the agent."""

    @property
    def session_id(self) -> str | None:
        """The agent's session, which a later run can resume; None until the agent provider has made it."""
        ...

    async def steer(
        self,
        message: str,
        origin: str | None = None,
        references: list[Path] | None = None,
        marks: list[Mark] | None = None,
    ) -> None:
        """Send the agent a message while it works, with images to show it and marks on the image."""
        ...


class DesignInProcessRun(InProcessRun):
    """An image's agent this process runs. Its record is kept with the image's agent's runs."""

    needs_image = False

    @property
    def session_id(self) -> str | None:
        return self._run.session_id

    def _save(self) -> None:
        self._image.save_designs()

    async def steer(
        self,
        message: str,
        origin: str | None = None,
        references: list[Path] | None = None,
        marks: list[Mark] | None = None,
    ) -> None:
        if self._task.done():
            raise _ended(self.name)
        sent = await asyncio.to_thread(steering.prepared, message, references or [], marks or [], self.name)
        send(self._folder, message, origin, sent, marks or [])


class DesignDetachedRun(DetachedRun):
    """An image's agent a process of its own runs."""

    @property
    def session_id(self) -> str | None:
        return self._record().session_id

    def _records(self) -> list[ImageRunRecord]:
        return load_designs(self.folder)

    async def steer(
        self,
        message: str,
        origin: str | None = None,
        references: list[Path] | None = None,
        marks: list[Mark] | None = None,
    ) -> None:
        if not await asyncio.to_thread(self._running):
            raise _ended(self.name)
        sent = await asyncio.to_thread(steering.prepared, message, references or [], marks or [], self.name)
        send(self._run_folder, message, origin, sent, marks or [])


def _ended(name: str) -> ImageDesignError:
    return ImageDesignError(
        f"The agent working on {name} has ended, so the message was not delivered. Start a new run with "
        "resume_session=True and the message as its prompt.",
        "not-running",
        name,
    )
