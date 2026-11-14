"""An agent provider faked for drawing SVGs: an agent that writes image.py and builds it in this process."""

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path
import runpy
from typing import Any
import uuid

import pytest

from image_design.capabilities.svg_image import build, draw
from image_design.intelligence.events import EventLog
from image_design.intelligence.schemas import AgentEvent, AgentEventKind, AgentRequest, AgentResult, Steering
from image_design.schemas import ImageDesignError
from image_design.shared.images import runs
from image_design.shared.images.store import SCRIPT, lock_path


def sailboat(sail: str = "#e63946") -> str:
    """An image.py that draws a sailboat of three named parts, as an agent would write it."""
    return f"""# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
from pathlib import Path

SAIL = "{sail}"
Path(__file__).with_name("image.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48" viewBox="0 0 64 48">'
    '<g id="sea"><rect y="32" width="64" height="16" fill="#1d3557"/></g>'
    '<g id="boat"><rect x="16" y="26" width="32" height="6" fill="#8d5524"/>'
    '<g id="sail"><polygon points="32,4 32,26 50,26" fill="' + SAIL + '"/></g></g></svg>',
    encoding="utf-8",
)
"""


class FakeAgentRun:
    """An agent that draws in its workspace as its behavior says, and records what it was sent."""

    def __init__(self, request: AgentRequest, behavior: "Behavior") -> None:
        self.request = request
        self.cancels = 0
        self.steered: list[tuple[str, list[Path]]] = []
        self.follow_ups: list[str] = []
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
    def work(self) -> Path:
        assert self.request.workspace is not None
        return self.request.workspace.path

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

    def calls(self, name: str, arguments: dict[str, Any]) -> str:
        """Emit a tool call as the agent providers do, and return its id, which its result carries."""
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        self.emit("tool_call", f"{name} {arguments}", tool_call_id=call_id, tool_name=name, arguments=arguments)
        return call_id

    def answers(self, call_id: str, name: str, result: str, success: bool = True) -> None:
        self.emit("tool_result", result, tool_call_id=call_id, tool_name=name, success=success, result=result)

    def writes(self, script: str) -> None:
        call_id = self.calls("Write", {"file_path": str(self.work / SCRIPT), "content": script})
        (self.work / SCRIPT).write_text(script, encoding="utf-8")
        self.answers(call_id, "Write", "")

    async def builds(self) -> None:
        command = build.command(self.work)
        call_id = self.calls("Bash", {"command": command})
        try:
            check = await asyncio.to_thread(build.build, self.work)
        except ImageDesignError as error:
            self.answers(call_id, "Bash", str(error), success=False)
            return
        self.answers(call_id, "Bash", check.describe())

    async def message(self) -> str:
        return await self._messages.get()

    async def finishes(self, text: str = "I drew a sailboat.") -> None:
        """End the turn as an agent does: act on each follow-up the run gives, then answer."""
        while self.request.follow_up is not None and (follow_up := await self.request.follow_up()) is not None:
            self.follow_ups.append(follow_up)
            await self.builds()
        self.emit("message", text)
        self.emit("usage", model="fake", input_tokens=100, output_tokens=20, cost={"USD": 0.01})
        self.end(AgentResult(text=text, session_id=self._session))


Behavior = Callable[[FakeAgentRun], Coroutine[Any, Any, None]]


def draws(sail: str = "#e63946", finding: str | None = None) -> Behavior:
    """An agent that writes the sailboat, builds it, and finishes; first checking image.py holds `finding`, if given."""

    async def behave(run: FakeAgentRun) -> None:
        if finding is not None:
            assert (run.work / SCRIPT).read_text(encoding="utf-8") == finding
        run.writes(sailboat(sail))
        await run.builds()
        await run.finishes()

    return behave


def steered_to(sail: str) -> Behavior:
    """An agent that draws, waits for a steering message, then redraws the sail."""

    async def behave(run: FakeAgentRun) -> None:
        run.writes(sailboat())
        await run.builds()
        await run.message()
        run.writes(sailboat(sail))
        await run.builds()
        await run.finishes()

    return behave


async def hangs(run: FakeAgentRun) -> None:
    await asyncio.Event().wait()


class FakeDrawingAgent:
    """Stands in for an agent provider, recording each agent it starts."""

    implementation = "fake"
    steering: Steering = "queued"

    def __init__(self) -> None:
        self.behavior: Behavior = draws()
        self.runs: list[FakeAgentRun] = []

    def preflight(self) -> None:
        pass

    async def start(self, request: AgentRequest) -> FakeAgentRun:
        run = FakeAgentRun(request, self.behavior)
        self.runs.append(run)
        return run


def run_in_process(work: Path) -> None:
    """image.py run in this process, as `uv run --script` runs it, so the tests start no process."""
    lock = lock_path(work / SCRIPT)
    if not lock.is_file():
        lock.write_text("version = 1\n", encoding="utf-8")
    try:
        runpy.run_path(str(work / SCRIPT), run_name="__main__")
    except Exception as error:
        raise ImageDesignError(
            f"`uv run --script image.py` failed with exit code 1:\n{type(error).__name__}: {error}", "build-failed"
        ) from None


def fake_agent(monkeypatch: pytest.MonkeyPatch) -> FakeDrawingAgent:
    """The agent provider faked, and image.py run in this process, for as long as `monkeypatch` lasts."""
    fake = FakeDrawingAgent()
    monkeypatch.setattr(draw, "resolve_agent_provider", lambda provider: provider or "codex")
    monkeypatch.setattr(draw, "select_intelligence", lambda intelligence, *_: (intelligence or fake, "fake-model"))
    monkeypatch.setattr(build, "run_script", run_in_process)
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)
    return fake
