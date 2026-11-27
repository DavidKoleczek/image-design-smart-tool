"""A run on an image: its work done by this process, or a detached run followed through the files its process writes."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Generator
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import signal
from types import FrameType
from typing import Any, Protocol

from image_design.schemas import (
    ImageDesignError,
    ImageEvent,
    ImageEventKind,
    ImageResult,
    ImageRunRecord,
    ImageRunStatus,
    ImageUsage,
    ImageVersion,
)
from image_design.shared.images.store import (
    EVENTS,
    PROCESS_LOG,
    Script,
    StoredImage,
    alive,
    load_runs,
    read_events,
    release_lock,
)

# How often a run looks for a cancel from another process, and a detached run's handle for new events.
POLL_SECONDS = 1.0
# Every signal that ends the process stops a run first, so nothing it started outlives it. SIGHUP is the console closing
# on Linux and macOS, and SIGBREAK is Windows' Ctrl+Break and console closing, which reaches a process group of its own.
STOPPING_SIGNALS = ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK")
CANCEL = "cancel"
PREVIEWS = "previews"


class ImageRun(Protocol):
    """An image being made: what happens as it happens, a way to stop it, and how it ended."""

    name: str
    directory: Path
    data_directory: Path
    run_id: str
    folder: Path
    """The image's folder in the data directory, where the run keeps its files under `runs/<run_id>`."""

    def events(self) -> AsyncIterator[ImageEvent]:
        """Every event from the start, then live ones until the run ends with `finished` or `failed`."""
        ...

    async def cancel(self) -> None:
        """Stop the run at once and wait for it to end."""
        ...

    async def result(self) -> ImageResult:
        """Wait for the run to end."""
        ...


class KeepImage(Protocol):
    def __call__(self, content: bytes, script: Script | None = None) -> None:
        """Keep an image the work made, and the script that built it, as a version, or as a draft's image."""
        ...


@dataclass(frozen=True)
class RunOutput:
    """Where a method's work sends what it receives, as it receives it."""

    preview: Callable[[bytes, int], None]
    image: KeepImage
    used: Callable[[ImageUsage], None]
    event: Callable[[ImageEventKind, str, dict[str, Any]], None]


Work = Callable[[RunOutput], Coroutine[Any, Any, None]]


class InProcessRun:
    """An image being made by work this process does.

    `stop` ends what was started for the work, such as an agent, once the work has ended however it ended. A cancel
    can come before the work's first step, when nothing in the work itself would run. Previews are kept with
    `preview_suffix`, which is `suffix` unless they come in another format, as a drawing's renders do. A draft, whose
    record names its `draft` file, keeps its image there rather than as a version, and holds no `lock`.
    """

    # Whether work that ends without keeping an image has failed. An agent that directs image calls makes none itself.
    needs_image = True

    def __init__(
        self,
        image: StoredImage,
        run: ImageRunRecord,
        work: Work,
        timeout_seconds: int | None,
        lock: Path | None,
        suffix: str,
        stop: Callable[[], Awaitable[None]] | None = None,
        preview_suffix: str | None = None,
    ) -> None:
        self.name = image.name
        self.directory = image.root
        self.data_directory = image.data
        self.run_id = run.id
        # The image's folder in the data directory, where a detached run's caller follows it.
        self.folder = image.folder
        self._image = image
        self._run = run
        self._timeout_seconds = timeout_seconds
        self._lock = lock
        self._suffix = suffix
        self._preview_suffix = preview_suffix or suffix
        self._stop = stop
        self._made: list[ImageVersion] = []
        self._drafted: Path | None = None
        self._events: list[ImageEvent] = []
        # Replaced on every append, so a reader waits on the one current when it ran out of events.
        self._appended = asyncio.Event()
        self._emit(
            "started",
            f"Making {self.name} with {run.request.get('model', run.method)}.",
            {
                "name": self.name,
                "directory": str(self.directory),
                "method": run.method,
                "origin": run.origin,
                "prompt": run.prompt,
                # The request names the files it was given relative to this.
                "run_folder": str(image.run_folder(run.id)),
                **run.request,
                **linked(run),
                **({"draft": str(image.folder / run.draft)} if run.draft is not None else {}),
            },
        )
        output = RunOutput(self._preview, self._keep, self._used, self._emit)
        self._working = asyncio.create_task(work(output))
        self._task = asyncio.create_task(self._drive())

    def events(self) -> AsyncIterator[ImageEvent]:
        """Every event from the start, then live ones until the run ends with `finished` or `failed`."""
        return self._replay()

    async def cancel(self) -> None:
        """Stop the run at once and wait for it to end."""
        self._working.cancel()
        await asyncio.wait([self._task])

    async def result(self) -> ImageResult:
        """Wait for the run to end."""
        return await asyncio.shield(self._task)

    @property
    def _folder(self) -> Path:
        return self._image.run_folder(self.run_id)

    async def _replay(self) -> AsyncIterator[ImageEvent]:
        index = 0
        while True:
            appended = self._appended
            while index < len(self._events):
                event = self._events[index]
                index += 1
                yield event
                if event.kind in ("finished", "failed"):
                    return
            if self._task.done():
                return
            await appended.wait()

    async def _drive(self) -> ImageResult:
        watcher = asyncio.create_task(self._watch())
        timed_out = False
        try:
            _, pending = await asyncio.wait([self._working], timeout=self._timeout_seconds)
            if pending:
                timed_out = True
                self._working.cancel()
                await asyncio.wait([self._working])
            # Awaited before the end is set below: from then on a reader's wait returns at once, so it never yields.
            if self._stop is not None:
                with contextlib.suppress(Exception):
                    await self._stop()
        except asyncio.CancelledError:
            # The caller's loop is ending with the run in it, so the run ends with it.
            self._working.cancel()
            self._end("cancelled", "The process running the request stopped before the request ended.")
            raise
        finally:
            watcher.cancel()
            # Set for good, so readers waiting on it see the run end.
            self._appended.set()
        status: ImageRunStatus
        error: str | None = None
        if timed_out:
            status = "timed-out"
            error = (
                f"The request did not finish within {self._timeout_seconds} seconds and was stopped. Give it more "
                "time with timeout_seconds (--timeout-seconds)."
            )
        elif self._working.cancelled():
            status = "cancelled"
        elif (failure := self._working.exception()) is not None:
            status = "failed"
            error = str(failure) if isinstance(failure, ImageDesignError) else f"{type(failure).__name__}: {failure}"
        elif not self._made and self._drafted is None and self.needs_image:
            status = "failed"
            error = "The request ended without an image. Try it again, or change the prompt."
        else:
            status = "done"
        self._end(status, error)
        result = ImageResult(
            name=self.name,
            path=self._image.path,
            directory=self.directory,
            data_directory=self.data_directory,
            run_id=self.run_id,
            status=status,
            versions=[self._image.located(version) for version in self._made],
            draft=self._drafted,
            usage=self._run.usage,
            error=error,
        )
        if status in ("done", "cancelled"):
            self._emit("finished", _ending(result), result.model_dump(mode="json"))
        else:
            self._emit("failed", error or "", result.model_dump(mode="json"))
        return result

    async def _watch(self) -> None:
        """Act on a cancel another process asked for, as `cancel_image` does."""
        while True:
            if (self._folder / CANCEL).exists():
                self._working.cancel()
                return
            await asyncio.sleep(POLL_SECONDS)

    def _preview(self, content: bytes, index: int) -> None:
        path = self._folder / PREVIEWS / f"{index + 1}{self._preview_suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self._emit("preview", f"Preview {index + 1} of {self.name}: {path}", {"path": str(path), "index": index})

    def _keep(self, content: bytes, script: Script | None = None) -> None:
        if self._run.draft is not None:
            # A request makes one image, so a draft keeps the first it makes.
            if self._drafted is None:
                self._draft(self._image.folder / self._run.draft, content)
            return
        version = self._image.add_version(content, self._suffix, self._run.method, self.run_id, script)
        first = not self._made
        if first:
            self._image.publish(version)
        self._made.append(version)
        self._run.versions.append(version.id)
        located = self._image.located(version)
        shown = self._image.path if first else located.file
        self._emit("version", f"Saved {version.id} of {self.name}: {shown}", located.model_dump(mode="json"))

    def _draft(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self._drafted = path
        self._emit("draft", f"Saved draft {self.run_id} of {self.name}: {path}", {"path": str(path)})

    def _used(self, usage: ImageUsage) -> None:
        self._run.usage = usage
        self._save()

    def _save(self) -> None:
        """Keep the run's record as it is now, where the image's runs are kept."""
        self._image.save_run(self._run)

    def _end(self, status: ImageRunStatus, error: str | None) -> None:
        self._run.status = status
        self._run.error = error
        self._run.finished = datetime.now(UTC)
        self._save()
        if self._lock is not None:
            release_lock(self._lock, self.run_id)

    def _emit(self, kind: ImageEventKind, text: str = "", data: dict[str, Any] | None = None) -> None:
        event = ImageEvent(run_id=self.run_id, kind=kind, text=text, data=data or {})
        self._folder.mkdir(parents=True, exist_ok=True)
        with (self._folder / EVENTS).open("a", encoding="utf-8") as events:
            events.write(json.dumps(event.model_dump(mode="json")) + "\n")
        self._run.last_event = event.time
        self._save()
        self._events.append(event)
        self._appended.set()
        self._appended = asyncio.Event()


class DetachedRun:
    """An image being made in a process of its own, followed through the files that process writes."""

    def __init__(self, directory: Path, data_directory: Path, folder: Path, name: str, run_id: str) -> None:
        self.name = name
        self.directory = directory
        self.data_directory = data_directory
        self.run_id = run_id
        self.folder = folder

    def events(self) -> AsyncIterator[ImageEvent]:
        """Every event from the start, then each as the run's process writes it, until the run ends."""
        return self._follow()

    async def cancel(self) -> None:
        """Stop the run at once and wait for it to end."""
        if await asyncio.to_thread(self._running):
            (self._run_folder / CANCEL).touch()
        await self.result()

    async def result(self) -> ImageResult:
        """Wait for the run to end."""
        last: ImageEvent | None = None
        async for event in self._follow():
            last = event
        if last is not None and last.kind in ("finished", "failed"):
            return ImageResult.model_validate(last.data)
        run = self._record()
        return ImageResult(
            name=self.name,
            path=self.directory / self.name,
            directory=self.directory,
            data_directory=self.data_directory,
            run_id=self.run_id,
            status="failed",
            error=f"The process running the request, {run.pid}, ended before the request did. What it printed is in "
            f"{self._run_folder / PROCESS_LOG}.",
        )

    @property
    def _run_folder(self) -> Path:
        return self.folder / "runs" / self.run_id

    def _record(self) -> ImageRunRecord:
        return next(run for run in self._records() if run.id == self.run_id)

    def _records(self) -> list[ImageRunRecord]:
        """The records of the kind of run this is, among which its own is kept."""
        return load_runs(self.folder)

    def _running(self) -> bool:
        run = self._record()
        return run.status == "running" and alive(run.pid)

    async def _follow(self) -> AsyncIterator[ImageEvent]:
        path = self._run_folder / EVENTS
        offset = 0
        while True:
            # Looked at before reading, so every event of a run seen to have ended is read.
            ended = not await asyncio.to_thread(self._running)
            events, offset = await asyncio.to_thread(read_events, path, offset)
            for event in events:
                yield event
                if event.kind in ("finished", "failed"):
                    return
            if ended:
                return
            await asyncio.sleep(POLL_SECONDS)


def linked(run: ImageRunRecord) -> dict[str, str]:
    """What a run's `started` event says of the agent's run that made it."""
    links = {"parent": run.parent, "parent_image": run.parent_image}
    return {key: value for key, value in links.items() if value is not None}


@contextlib.contextmanager
def stopped_by_signals(run: ImageRun) -> Generator[None]:
    """Stop the run on every signal that ends the process."""
    loop = asyncio.get_running_loop()
    stopping: set[asyncio.Task[None]] = set()

    def stop() -> None:
        task = asyncio.ensure_future(run.cancel())
        stopping.add(task)
        task.add_done_callback(stopping.discard)

    def handler(signum: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop)

    previous: dict[signal.Signals, Any] = {}
    for name in STOPPING_SIGNALS:
        number = getattr(signal, name, None)
        if isinstance(number, signal.Signals):
            previous[number] = signal.signal(number, handler)
    try:
        yield
    finally:
        for number, original in previous.items():
            signal.signal(number, original)


def _ending(result: ImageResult) -> str:
    if result.status == "cancelled":
        return f"Cancelled the request on {result.name}." + (
            f" It made {len(result.versions)} image(s) first." if result.versions else ""
        )
    used = ""
    if result.usage is not None:
        used = f" Used {result.usage.output_tokens:,} output tokens"
        used += f", about ${result.usage.cost:.3f}." if result.usage.cost is not None else "."
    return f"Done: {result.draft or result.path}.{used}"
