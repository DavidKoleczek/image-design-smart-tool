"""What the image's agent is told of the image's calls: those made since its last turn, or the image's history for a
new session, each written as the command that would make it, with what it made.

A session goes on knowing what it did, so what it is told is what it cannot know: calls the person made, its own calls
that ended after its turn did, and calls of another session.
"""

from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import NamedTuple

from image_design.schemas import ImageRunRecord
from image_design.shared.images.requests import REFERENCE_PREFIX
from image_design.shared.images.store import StoredImage, image_by_id

# How many of an image's calls a new session is told of, the latest ones. The rest are a command away, so the prompt
# stays about the request.
HISTORY_SHOWN = 3
# The options of a call that are written as they were recorded, in the order the command takes them.
OPENAI_OPTIONS = (
    ("model", "--model"),
    ("quality", "--quality"),
    ("complexity", "--complexity"),
    ("background", "--background"),
    ("compression", "--compression"),
    ("frames", "--frames"),
    ("frame_ms", "--frame-ms"),
)
PLAIN = re.compile(r"^[\w./:\\-]+$")

HISTORY = "## The image's history"
SINCE = "## Since your last turn"
HISTORY_INTRO = "The calls made on it so far, oldest first."
LEFT_OUT = "The last {shown} of the {total} calls made on it, oldest first."
# How to find out more than the prompt tells of the image's calls, said after either of the above.
MORE = (
    "For more, `image-design read-image-activity --name {name} --json` has every call: the `started` event of each has "
    "its prompt, its settings, and the files it sent. The files each call was given and made are also in the folder "
    "named by its id under {runs}."
)
YOUR_CALL = "1. Your call {run}{where}, which you made as:"
ANOTHER_SESSION = "1. Another session of the image's agent made the call {run}{where} as:"
SOMEONE = "1. {who} made the call {run}{where} as:"
ON = " on {name}"
WITH_PROMPT = "with the prompt:"
PERSON = "The person, in the app,"
COMMAND_LINE = "Someone, from the command line,"
MADE = "It made {versions}.{current}"
NO_VERSION = "no version"
NOW_THE_FILE = " It is now the image's file."
DRAFTED = "It made a draft, kept apart from the image's versions: {path}.{kept}"
KEPT_AS = " It was then kept as {versions}."
RUNNING = "It is still running."
STOPPED = "It was stopped before it ended, and made {versions}."
NOTHING = "nothing"
ENDED = "It {status}: {error}"
NO_REASON = "no reason was given."
MARKS_LAYER = "and marks, sent as a layer: {path}"
MARKS_DRAWN = "and marks, drawn on a copy: {path}"
NO_VERSIONS = "it has no versions yet"
ONE_VERSION = "its only version is {version}"
VERSION_RANGE = "its versions are {first} to {last}"
NO_FILE = "It has no file yet, and {versions}."
NOT_MADE = "Its file was not made by the tool, and {versions}."
CHANGED = "Its file was changed outside the tool since the tool last wrote it, and {versions}."
HOLDS = "Its file holds {current}, and {versions}."


class Call(NamedTuple):
    """An image call, and the image it is on, which is not the agent's image for a call it made on another."""

    image: StoredImage
    run: ImageRunRecord


def calls_of(image: StoredImage) -> list[Call]:
    """The calls on the image and those its agent made on other images, in the order they started."""
    found = [Call(image, run) for run in image.runs]
    for image_id, run_id in image.linked():
        other = image_by_id(image.root, image.data, image_id)
        run = next((run for run in other.runs if run.id == run_id), None) if other is not None else None
        if other is not None and run is not None:
            found.append(Call(other, run))
    return sorted(found, key=lambda call: call.run.started)


def history(image: StoredImage) -> list[Call]:
    """What a new session is told: every call of the image's conversation."""
    return calls_of(image)


def since(image: StoredImage, session: list[ImageRunRecord]) -> list[Call]:
    """What a session going on is told: each call it has not seen as it now is.

    A session saw a call it made itself end when that ended before its turn did. What it was told before, it saw as it
    was then, so a call told while it ran is told again once it ends.
    """
    turns = {turn.id: turn for turn in session}
    told: dict[str, str] = {}
    for turn in session:
        told |= turn.request.get("told") or {}
    unseen: list[Call] = []
    for call in calls_of(image):
        run = call.run
        if told.get(run.id) == run.status:
            continue
        turn = turns.get(run.parent or "")
        if turn is not None and _before(run.finished, turn.finished):
            continue
        unseen.append(call)
    return unseen


def describe(calls: list[Call], image: StoredImage, session: list[ImageRunRecord], new: bool) -> str:
    """The section a prompt tells the calls in, or nothing when there are none."""
    if not calls:
        return ""
    turns = {turn.id for turn in session}
    shown = calls[-HISTORY_SHOWN:] if new else calls
    lines = [HISTORY if new else SINCE, ""]
    if new:
        heading = LEFT_OUT.format(shown=len(shown), total=len(calls)) if len(shown) < len(calls) else HISTORY_INTRO
        more = MORE.format(name=argument(image.name), runs=image.runs_folder)
        lines += [f"{heading} {more}", ""]
    for call in shown:
        lines += [*_told(call, turns, image), ""]
    return "\n".join(lines).rstrip() + "\n"


def told(calls: list[Call]) -> dict[str, str]:
    """How each call was when it was told, which a later turn of the session is not told again."""
    return {call.run.id: call.run.status for call in calls}


def state(image: StoredImage) -> str:
    """What the image's file holds now, and its versions, as the range they run over."""
    kept = image.versions.versions
    if not kept:
        versions = NO_VERSIONS
    elif len(kept) == 1:
        versions = ONE_VERSION.format(version=kept[0].id)
    else:
        versions = VERSION_RANGE.format(first=kept[0].id, last=kept[-1].id)
    if not image.path.is_file():
        return NO_FILE.format(versions=versions)
    if not kept:
        return NOT_MADE.format(versions=versions)
    if image.versions.current is None or not image.current_file_matches():
        return CHANGED.format(versions=versions)
    return HOLDS.format(current=image.versions.current, versions=versions)


def command(call: Call) -> str:
    """The command that would make the call again, without its prompt."""
    image, run = call
    folder = image.run_folder(run.id)
    request = run.request
    parts = [f"image-design generate-{run.method}-image", "--name", argument(image.name)]
    if isinstance(version := request.get("version"), str):
        parts += ["--version", version]
    if run.draft is not None:
        parts.append("--draft")
    for sent in request.get("images") or []:
        if PurePosixPath(sent).name.startswith(REFERENCE_PREFIX):
            parts += ["--reference", argument(str(folder / sent))]
    if run.method == "openai":
        for field, flag in OPENAI_OPTIONS:
            if request.get(field) is not None:
                parts += [flag, str(request[field])]
        size = request.get("size")
        if isinstance(size, list) and len(size) == 2:
            parts += ["--size", f"{size[0]}x{size[1]}"]
        if isinstance(mask := request.get("mask"), str):
            parts += ["--mask", argument(str(folder / mask))]
    elif request.get("transparent"):
        parts.append("--transparent")
    return " ".join(parts)


def _told(call: Call, turns: set[str], image: StoredImage) -> list[str]:
    run = call.run
    where = "" if call.image is image else ON.format(name=call.image.name)
    if run.parent is not None and run.parent in turns:
        head = YOUR_CALL.format(run=run.id, where=where)
    elif run.parent is not None:
        head = ANOTHER_SESSION.format(run=run.id, where=where)
    else:
        head = SOMEONE.format(who=_who(run.origin), run=run.id, where=where)
    marks = _marks(call)
    lines = [head, f"   {command(call)}", f"   {WITH_PROMPT}", *_indented(run.prompt, "     ")]
    if marks:
        lines.append(f"   {marks}")
    lines.append(f"   {_outcome(call)}")
    return lines


def _who(origin: str | None) -> str:
    if origin == "app":
        return PERSON
    if origin is None:
        return COMMAND_LINE
    return origin


def _outcome(call: Call) -> str:
    image, run = call
    match run.status:
        case "done" if run.draft is not None:
            kept = KEPT_AS.format(versions=", ".join(run.versions)) if run.versions else ""
            return DRAFTED.format(path=image.folder / run.draft, kept=kept)
        case "done":
            current = NOW_THE_FILE if run.versions[:1] == [image.versions.current] else ""
            return MADE.format(versions=", ".join(run.versions) or NO_VERSION, current=current)
        case "running":
            return RUNNING
        case "cancelled":
            return STOPPED.format(versions=", ".join(run.versions) or NOTHING)
    return ENDED.format(status=run.status, error=run.error or NO_REASON)


def _marks(call: Call) -> str:
    """Where the marks a call drew are, which its command cannot name, since they were given as shapes."""
    folder = call.image.run_folder(call.run.id)
    if isinstance(markup := call.run.request.get("markup"), str):
        return MARKS_LAYER.format(path=folder / markup)
    marked = [sent for sent in call.run.request.get("images") or [] if PurePosixPath(sent).stem == "marked"]
    return MARKS_DRAWN.format(path=folder / marked[0]) if marked else ""


def _before(finished: datetime | None, turn_finished: datetime | None) -> bool:
    return finished is not None and turn_finished is not None and finished <= turn_finished


def _indented(text: str, prefix: str) -> list[str]:
    return [f"{prefix}{line}" if line else "" for line in text.strip().splitlines()] or [f"{prefix}(empty)"]


def argument(value: str) -> str:
    """`value` as a command line takes it: as it is, or quoted when it has a space or another character a shell reads."""
    return value if PLAIN.match(value) else '"' + value.replace('"', '\\"') + '"'
