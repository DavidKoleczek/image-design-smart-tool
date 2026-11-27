"""Detached runs: a request run in a process of its own, apart from the caller's, so the run outlives the caller.

The caller starts the launcher with the request on its stdin. The launcher starts the run's process apart from the
caller's console, session, and job, and exits. That process starts the run and reports one line on stdout once the run
is going or cannot be.
"""

import asyncio
from collections.abc import Awaitable, Callable
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, TextIO

from pydantic import BaseModel

from image_design.schemas import ImageDesignError
from image_design.shared.images import launch
from image_design.shared.images.runs import DetachedRun, ImageRun, stopped_by_signals
from image_design.shared.images.store import PROCESS_LOG

LAUNCHER = [sys.executable, "-m", launch.__name__]


async def detach[Run: DetachedRun](
    command: list[str], request: BaseModel, directory: Path, data_directory: Path, follow: type[Run]
) -> Run:
    """Start `command` with `request`, and follow the run it reports as a `follow`."""
    report = await asyncio.to_thread(_start_process, command, request)
    if report.get("error"):
        raise ImageDesignError(report["error"], report.get("reason"), report.get("image"))
    return follow(directory, data_directory, Path(report["folder"]), report["name"], report["run_id"])


def serve(start: Callable[[str], Awaitable[ImageRun]]) -> int:
    """Run the request on stdin to its end with `start`, as the process a detached run runs in."""
    # The report goes out on a copy of stdout, and stdout itself goes nowhere until the run starts, so nothing else
    # printed can garble the report.
    report = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    sys.stdout.flush()
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return asyncio.run(_serve(start, sys.stdin.buffer.read().decode("utf-8"), report))


async def _serve(start: Callable[[str], Awaitable[ImageRun]], request: str, report: TextIO) -> int:
    with report:
        try:
            run = await start(request)
        except ImageDesignError as error:
            _report(report, {"error": str(error), "reason": error.reason, "image": error.image})
            return 1
        except Exception as error:  # whatever stopped it, the caller is waiting to hear
            _report(
                report, {"error": f"The run did not start: {type(error).__name__}: {error}", "reason": "start-failed"}
            )
            return 1
        _log_to(run.folder / "runs" / run.run_id / PROCESS_LOG)
        _report(report, {"name": run.name, "run_id": run.run_id, "folder": str(run.folder)})
    with stopped_by_signals(run):
        result = await run.result()
    return 0 if result.status == "done" else 1


def _start_process(command: list[str], request: BaseModel) -> dict[str, Any]:
    """Start the process a detached run runs in, and return what it reports once the run is going or cannot be."""
    process = launch.detached_process([*LAUNCHER, *command], subprocess.PIPE, subprocess.PIPE)
    # The launcher only starts the run's own process and exits; waited on here so it leaves no zombie.
    threading.Thread(target=process.wait, daemon=True).start()
    assert process.stdin is not None
    assert process.stdout is not None
    with process.stdin:
        process.stdin.write(request.model_dump_json().encode("utf-8"))
    with process.stdout:
        line = process.stdout.readline()
    if not line:
        return {
            "error": "The process that runs the request ended before the request started, without saying why. Run the "
            "request without detach to see why.",
            "reason": "start-failed",
        }
    return json.loads(line)


def _report(report: TextIO, message: dict[str, str | None]) -> None:
    report.write(json.dumps(message) + "\n")
    report.flush()


def _log_to(path: Path) -> None:
    """Send what this process prints from now on to the run's log, beside its events."""
    sys.stdout.flush()
    sys.stderr.flush()
    log = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    os.dup2(log, sys.stdout.fileno())
    os.dup2(log, sys.stderr.fileno())
    os.close(log)
