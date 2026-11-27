"""An agent provider faked for `design_image`: an agent that makes image calls through the library, as the real one
makes them through the CLI, with the environment its run gives its processes."""

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path
from typing import Any
import uuid

import pytest

from image_design import lib
from image_design.capabilities.design_image import design, tooling
from image_design.intelligence.events import EventLog
from image_design.intelligence.schemas import AgentEvent, AgentEventKind, AgentRequest, AgentResult, Steering
from image_design.schemas import ImageDesignError, ImageResult
from image_design.shared.images import calls, runs


class FakeDesignRun:
    """An agent that works as its behavior says, and records what it was sent."""

    def __init__(self, request: AgentRequest, behavior: "Behavior") -> None:
        self.request = request
        self.cancels = 0
        self.steered: list[tuple[str, list[Path]]] = []
        self._session = request.resume or f"session-{uuid.uuid4().hex[:6]}"
        self._messages: asyncio.Queue[str] = asyncio.Queue()
        self._log = EventLog()
        self._ended: asyncio.Future[AgentResult] = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(behavior(self))
        self._task.add_done_callback(self._raised)

    def _raised(self, task: asyncio.Task[None]) -> None:
        """End the run with what a behavior raised, so a test shows it rather than waiting out the run."""
        if not task.cancelled() and (error := task.exception()) is not None:
            self.end(AgentResult(error=f"The fake agent raised {error!r}", session_id=self._session))

    @property
    def session_id(self) -> str | None:
        return self._session

    @property
    def parent(self) -> str:
        """The agent's run, as its processes are told it."""
        return self.request.environment[calls.PARENT]

    def events(self) -> AsyncIterator[AgentEvent]:
        return self._log.replay()

    async def steer(self, message: str, images: list[Path] | None = None) -> None:
        if self._ended.done():
            raise ImageDesignError("The agent run has ended, so the steering message was not delivered.")
        self.steered.append((message, list(images or [])))
        self._messages.put_nowait(message)

    async def cancel(self) -> None:
        self.cancels += 1
        self._task.cancel()
        await asyncio.wait([self._task])
        self.end(AgentResult(cancelled=True, session_id=self._session))

    async def result(self) -> AgentResult:
        return await self._ended

    def emit(self, kind: AgentEventKind, text: str = "", **data: Any) -> None:
        self._log.emit(AgentEvent(kind=kind, text=text, data=data))

    def end(self, result: AgentResult) -> None:
        if not self._ended.done():
            self._ended.set_result(result)
            self._log.emit(AgentEvent(kind="terminal", text=result.error or result.text, data=result.model_dump()))

    async def generates(self, prompt: str, name: str, **arguments: Any) -> ImageResult:
        """Make an image call as the agent's shell would, and see what the command printed."""
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        command = f"image-design generate-openai-image {prompt!r} --name {name}"
        self.emit(
            "tool_call", f"Bash {command}", tool_call_id=call_id, tool_name="Bash", arguments={"command": command}
        )
        try:
            made = await lib.generate_openai_image(prompt=prompt, name=name, parent=self.parent, **arguments)
            result = await made.result()
        except ImageDesignError as error:
            self.emit("tool_result", str(error), tool_call_id=call_id, tool_name="Bash", success=False)
            raise
        said = result.error or "\n".join(str(version.file) for version in result.versions) or result.status
        self.emit("tool_result", said, tool_call_id=call_id, tool_name="Bash", success=result.status == "done")
        return result

    async def message(self) -> str:
        return await self._messages.get()

    def finishes(self, text: str = "I made the image.") -> None:
        self.emit("message", text)
        self.emit("usage", model="fake", input_tokens=200, output_tokens=40, cost={"USD": 0.02})
        self.end(AgentResult(text=text, session_id=self._session))


Behavior = Callable[[FakeDesignRun], Coroutine[Any, Any, None]]


def edits(name: str = "cactus.png", prompt: str = "Remove the flower bud from image 1.", **arguments: Any) -> Behavior:
    """An agent that makes one call on `name` and finishes."""

    async def behave(run: FakeDesignRun) -> None:
        await run.generates(prompt, name, **arguments)
        run.finishes()

    return behave


def makes(*names: str) -> Behavior:
    """An agent that makes one call on each of `names`, in turn, and finishes."""

    async def behave(run: FakeDesignRun) -> None:
        for name in names:
            await run.generates(f"A variant for {name}.", name)
        run.finishes()

    return behave


def says(text: str) -> Behavior:
    """An agent that makes no call, as when it asks a question."""

    async def behave(run: FakeDesignRun) -> None:
        run.finishes(text)

    return behave


async def says_where_it_runs(run: FakeDesignRun) -> None:
    """An agent that says the directory it was started in, and finishes."""
    assert run.request.workspace is not None
    run.finishes(str(run.request.workspace.path))


def waits_for_a_message() -> Behavior:
    async def behave(run: FakeDesignRun) -> None:
        heard = await run.message()
        run.finishes(f"Heard: {heard}")

    return behave


async def hangs(run: FakeDesignRun) -> None:
    await asyncio.Event().wait()


class FakeDesignAgent:
    """Stands in for an agent provider, recording each agent it starts."""

    implementation = "fake"
    steering: Steering = "queued"

    def __init__(self) -> None:
        self.behavior: Behavior = says("Nothing to do.")
        self.runs: list[FakeDesignRun] = []

    def preflight(self) -> None:
        pass

    async def start(self, request: AgentRequest) -> FakeDesignRun:
        run = FakeDesignRun(request, self.behavior)
        self.runs.append(run)
        return run


def fake_designer(monkeypatch: pytest.MonkeyPatch, state: Path) -> FakeDesignAgent:
    """The agent provider faked, with what it is given written to `state`, for as long as `monkeypatch` lasts."""
    fake = FakeDesignAgent()
    monkeypatch.setattr(design, "resolve_agent_provider", lambda provider: provider or "claude")
    monkeypatch.setattr(design, "select_intelligence", lambda intelligence, *_: (intelligence or fake, "fake-model"))
    monkeypatch.setattr(tooling, "state_directory", lambda: state)
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)
    return fake
