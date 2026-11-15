"""How the image's agent reaches the tool: a command on its PATH that runs this installation's CLI, the tool's own
skill, and the skills for the craft."""

import hashlib
from pathlib import Path
import secrets
import shlex
import shutil
import sys

import yaml

from image_design.core.manifest import load_manifest
from image_design.core.skill import DISTRIBUTION, skill
from image_design.shared.state import state_directory

# The skills for the craft of image calls, each a folder holding a SKILL.md.
CRAFT = Path(__file__).parent / "craft"
CRAFT_SKILLS = tuple(sorted(path.parent.name for path in CRAFT.glob("*/SKILL.md")))
FRONTMATTER = "---"
# How much of a content hash names a folder written for runs to share.
HASH_LENGTH = 16


def command_directory() -> Path:
    """A folder holding only `image-design`, which runs the CLI of the environment this process runs in.

    The agent's shell may find another installation, or none, on its own PATH. On Windows a .cmd serves PowerShell and
    cmd, and a script without an extension serves the POSIX shells, such as Git Bash, that Claude Code runs commands in.
    """
    python = Path(sys.executable)
    posix = f'#!/bin/sh\nexec {shlex.quote(python.as_posix())} -m image_design.cli "$@"\n'
    files = {DISTRIBUTION: posix}
    if sys.platform == "win32":
        files[f"{DISTRIBUTION}.cmd"] = f'@echo off\r\n"{python}" -m image_design.cli %*\r\nexit /b %errorlevel%\r\n'
    return _written("bin", files, executable=True)


def skill_directories() -> list[Path]:
    """The skills the agent is given: those for the craft, and the tool's own, as a host agent reads it."""
    manifest = load_manifest()
    frontmatter = yaml.safe_dump({"name": DISTRIBUTION, "description": manifest.description}, width=1000)
    tool = _written("skills", {f"{DISTRIBUTION}/SKILL.md": f"---\n{frontmatter}---\n\n{skill()}\n"})
    return [CRAFT, tool]


def craft_skill(name: str) -> str:
    """The text of the craft skill `name`, without its frontmatter, as a prompt gives it in full."""
    text = (CRAFT / name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith(FRONTMATTER):
        text = text.split(FRONTMATTER, 2)[2]
    return text.strip()


def _written(kind: str, files: dict[str, str], executable: bool = False) -> Path:
    """A folder of `kind` in the tool's state holding `files`, named by their content, so a folder once written never
    changes and runs at once can share it."""
    digest = hashlib.sha256()
    for name, text in sorted(files.items()):
        digest.update(f"{name}\0{text}\0".encode())
    folder = state_directory() / kind / digest.hexdigest()[:HASH_LENGTH]
    if folder.is_dir():
        return folder
    # Written aside and renamed, so a run never finds half of it.
    partial = folder.with_name(f"{folder.name}.{secrets.token_hex(3)}.tmp")
    for name, text in files.items():
        path = partial / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        if executable:
            path.chmod(0o755)
    try:
        partial.rename(folder)
    except OSError:
        # Another run wrote the same folder first.
        shutil.rmtree(partial, ignore_errors=True)
        if not folder.is_dir():
            raise
    return folder
