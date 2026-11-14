"""What an intelligence implementation is asked to do, what it reports while it works, and what it answers with."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from image_design.schemas import DEFAULT_REASONING_EFFORT, ReasoningEffort

# How a steering message lands: in the current turn, when the agent next reads input, or by restarting the run.
Steering = Literal["mid-turn", "queued", "restart"]
AgentEventKind = Literal["message", "reasoning", "tool_call", "tool_result", "image", "usage", "terminal"]
# The image types an agent can be shown inline, by file suffix.
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class HostWorkspace(BaseModel):
    """A directory on this machine the agent works in, with the caller's own permissions."""

    path: Path


class AgentRequest(BaseModel):
    """One agent run: a prompt, a model, and optionally a place to work and a shape to answer in."""

    prompt: str
    model: str
    images: list[Path] = Field(default_factory=list, description="Images shown to the agent with the prompt")
    workspace: HostWorkspace | None = Field(
        default=None, description="Where the agent may read and run things; None means a plain completion, no tools"
    )
    writable: bool = Field(default=False, description="Whether the agent may create and modify files in the workspace")
    output_schema: dict[str, Any] | None = Field(
        default=None, description="JSON schema the structured output must satisfy; None asks for text only"
    )
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT
    timeout_seconds: int | None = Field(gt=0, description="None for no limit")
    resume: str | None = Field(
        default=None,
        description="The session_id of an earlier result to continue in, so the agent keeps what it learned; None starts fresh",
    )
    session_directory: Path | None = Field(
        default=None,
        description="Where the session is also kept, so it can be read and resumed from there; None keeps it only "
        "where the agent provider keeps its sessions",
    )
    skill_directories: list[Path] = Field(
        default_factory=list, description="Directories of Agent Skills, a folder holding a SKILL.md each, it may use"
    )
    generated_images: Path | None = Field(
        default=None,
        description="Where each image the agent makes with the agent provider's image tool is saved, announced by an "
        "`image` event; None means it cannot make images",
    )
    follow_up: Callable[[], Awaitable[str | None]] | None = Field(
        default=None,
        exclude=True,
        description="Asked each time the agent ends a turn with nothing queued; a message it gives goes on in the same "
        "session, and none lets the run end",
    )


class AgentEvent(BaseModel):
    """One thing the agent did, in the same shape for every agent provider; `terminal` comes last, once.

    An `image` event has the `path` of an image the agent made, and the `prompt` the image tool received.
    """

    time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: AgentEventKind
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """The run's outcome; in-flight agent failures set `error` instead of raising."""

    output: dict[str, Any] | None = Field(
        default=None, description="The structured output, conforming to the request's schema when one was given"
    )
    text: str = Field(default="", description="The agent's final message")
    error: str | None = None
    cancelled: bool = Field(default=False, description="Whether the run ended because it was cancelled")
    session_id: str | None = Field(
        default=None, description="Identifies this run's session so a later request can resume it"
    )
