"""Build a drawing in its work folder: run its image.py with uv, render the image.svg it writes, and measure it.

The agent drawing it runs this as a command, and the run builds once more as the agent finishes, so the SVG kept is
always one its image.py builds.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from pydantic import BaseModel

from image_design.capabilities.svg_image import measure
from image_design.schemas import ImageDesignError, SvgBudgets, SvgCheck
from image_design.shared.images import pictures
from image_design.shared.images.store import SCRIPT, lock_path

# What the agent runs, with the work folder after it. The tool's own Python, since `image-design` need not be on the
# agent's PATH, and a library caller has no command at all.
COMMAND = [sys.executable, "-m", "image_design.capabilities.svg_image.build"]
SVG = "image.svg"
RENDER = "render.png"
# What the run tells the build that the agent's command does not repeat: the image's name and its budgets.
DRAWING = ".drawing.json"
# The image.py the last build ran and whether it built, which says whether the agent saw what its last change drew.
BUILT = ".built.json"
SCRIPT_TIMEOUT_SECONDS = 300
UV_DOCUMENTATION = "https://docs.astral.sh/uv/getting-started/installation/"
# The end of what a failed step printed, which is where its error is.
OUTPUT_TAIL_CHARACTERS = 2000


class Drawing(BaseModel):
    """The drawing a work folder holds: the image it is for, and the budgets it is drawn to."""

    name: str
    budgets: SvgBudgets


def command(work: Path) -> str:
    """The command line that builds the drawing in `work`, quoted for a shell."""
    return " ".join(f'"{part}"' if " " in part or "\\" in part else part for part in [*COMMAND, str(work)])


def write_drawing(work: Path, drawing: Drawing) -> None:
    (work / DRAWING).write_text(drawing.model_dump_json(indent=2), encoding="utf-8")


def build(work: Path) -> SvgCheck:
    """Run image.py, render the SVG it wrote to render.png, and measure it; raise naming what went wrong."""
    drawing = Drawing.model_validate_json((work / DRAWING).read_text(encoding="utf-8"))
    script = work / SCRIPT
    digest = _digest(script)
    try:
        if digest is None:
            raise ImageDesignError(f"There is no {SCRIPT} in {work}. Write it first.", "build-failed")
        (work / SVG).unlink(missing_ok=True)
        run_script(work)
        if not (work / SVG).is_file():
            raise ImageDesignError(
                f"{SCRIPT} ran but wrote no {SVG}. Make it write {SVG} beside itself.", "build-failed"
            )
        content = (work / SVG).read_bytes()
        (work / RENDER).write_bytes(pictures.svg_png(content, work))
        check = SvgCheck(
            name=drawing.name, path=work / SVG, budgets=drawing.budgets, **measure.measure(content)._asdict()
        )
    except ImageDesignError:
        _record(work, digest, built=False)
        raise
    _record(work, digest, built=True)
    return check


def built(work: Path) -> bool:
    """Whether the last build ran image.py as it is now, and built."""
    try:
        record = json.loads((work / BUILT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return record.get("built") is True and record.get("sha256") == _digest(work / SCRIPT)


def run_script(work: Path) -> None:
    """Run image.py with uv, locking its dependencies first when it has no lock."""
    uv = shutil.which("uv")
    if uv is None:
        raise ImageDesignError(
            f"uv is not on PATH, and it is what runs {SCRIPT}. Install it as {UV_DOCUMENTATION} describes.",
            "not-set-up",
        )
    # The environment the tool runs in is not the script's, which uv makes for it.
    environment = {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}
    steps = [] if lock_path(work / SCRIPT).is_file() else [[uv, "lock", "--script", SCRIPT]]
    steps.append([uv, "run", "--script", SCRIPT])
    for step in steps:
        shown = "uv " + " ".join(step[1:])
        try:
            done = subprocess.run(
                step,
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=SCRIPT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ImageDesignError(
                f"`{shown}` did not finish within {SCRIPT_TIMEOUT_SECONDS} seconds. Make {SCRIPT} faster.",
                "build-failed",
            ) from None
        if done.returncode != 0:
            printed = "\n".join(part.strip() for part in (done.stdout, done.stderr) if part.strip())
            raise ImageDesignError(
                f"`{shown}` failed with exit code {done.returncode}:\n{printed[-OUTPUT_TAIL_CHARACTERS:]}",
                "build-failed",
            )


def main() -> int:
    """Build the drawing in the work folder named on the command line, and print how it measures."""
    if len(sys.argv) != 2:
        print(f"Pass the work folder: {' '.join(COMMAND)} <work folder>", file=sys.stderr)
        return 2
    work = Path(sys.argv[1]).resolve()
    try:
        check = build(work)
    except ImageDesignError as error:
        print(f"The build failed. {error}")
        return 1
    rendered = pictures.describe((work / RENDER).read_bytes())
    size = f" at {rendered.width}x{rendered.height}" if rendered is not None else ""
    print(f"Built {SVG} and rendered it to {RENDER}{size}. Look at {RENDER}.\n\n{check.describe()}")
    return 0


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _record(work: Path, digest: str | None, built: bool) -> None:
    (work / BUILT).write_text(json.dumps({"sha256": digest, "built": built}), encoding="utf-8")


if __name__ == "__main__":
    # A pipe on Windows defaults to the ANSI code page, which cannot encode much of what a script prints.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
