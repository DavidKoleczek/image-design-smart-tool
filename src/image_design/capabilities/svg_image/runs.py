"""A drawing's run: an image run that also has the agent's session, and takes steering messages."""

import asyncio
from pathlib import Path
from typing import Protocol

from image_design.capabilities.svg_image import steering
from image_design.schemas import ImageDesignError, Mark
from image_design.shared.images.runs import DetachedRun, ImageRun, InProcessRun


class SvgRun(ImageRun, Protocol):
    """An SVG being drawn: an image run, the agent's session, and a way to steer the agent."""

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
        """Send the agent a message while it works, with images to show it and marks on its latest render."""
        ...


class SvgInProcessRun(InProcessRun):
    """A drawing whose agent this process runs."""

    @property
    def session_id(self) -> str | None:
        return self._run.session_id

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
        steering.send(self._folder, message, origin, sent, marks or [])


class SvgDetachedRun(DetachedRun):
    """A drawing whose agent a process of its own runs."""

    @property
    def session_id(self) -> str | None:
        return self._record().session_id

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
        steering.send(self._run_folder, message, origin, sent, marks or [])


def _ended(name: str) -> ImageDesignError:
    return ImageDesignError(
        f"The drawing of {name} has ended, so the message was not delivered. Start a new run with resume_session=True "
        "and the message as its prompt.",
        "not-running",
        name,
    )
