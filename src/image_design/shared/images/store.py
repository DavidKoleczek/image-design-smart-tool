"""An image directory on disk: each image's file, and what the tool keeps for it in the data directory.

The data directory holds a folder per image, named by the image's id so it stays put when the image moves:

    images/<id>/image.json      the record, committed with the project
    images/<id>/image.py        for a drawn SVG, the script that builds it, committed with its image.py.lock
    images/<id>/versions.json   every version, and which one is in the image's file
    images/<id>/versions/       the versions' files, and a drawn SVG's scripts
    images/<id>/runs.json       every request on the image
    images/<id>/runs/<run id>/  a run's events, the files it sent, and its previews
    images/<id>/work/           where an agent draws an SVG
    images/<id>/sessions/       the agents' sessions, which a later run can resume
    locks/                      which process is working on which image
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import sys
import tempfile
import time
from typing import NamedTuple
import uuid

from pydantic import BaseModel, ValidationError

from image_design.schemas import (
    IMAGE_FORMATS,
    SVG_SUFFIX,
    ImageDesignError,
    ImageEvent,
    ImageMethod,
    ImageRecord,
    ImageRunRecord,
    ImageRuns,
    ImageSummary,
    ImageVersion,
    ImageVersions,
)
from image_design.shared.images import pictures

DEFAULT_DIRECTORY = Path(".image-design")
DATA_FOLDER = ".agents"
IMAGES = "images"
LOCKS = "locks"
RECORD = "image.json"
SCRIPT = "image.py"
# uv writes a script's lock beside it, under the script's name with this added.
LOCK_SUFFIX = ".lock"
VERSIONS = "versions.json"
RUNS = "runs.json"
EVENTS = "events.jsonl"
PROCESS_LOG = "process.log"
SESSIONS = "sessions"
# Every extension an image's name can end in.
KEPT_SUFFIXES = (*IMAGE_FORMATS, SVG_SUFFIX)
GITIGNORE = Path(__file__).with_name("data.gitignore")
# A lock file is written just after it is made, so one still empty this soon after is being written, not abandoned.
LOCK_WRITE_SECONDS = 10
# Windows refuses to replace a file another process has open, such as a viewer reading runs.json, and to open one being
# replaced; both are brief.
REPLACE_ATTEMPTS = 20
REPLACE_WAIT_SECONDS = 0.05


def directories(directory: Path | None, data_directory: Path | None) -> tuple[Path, Path]:
    """The image directory and the data directory, resolved, with their defaults filled in."""
    root = (directory or DEFAULT_DIRECTORY).resolve()
    return root, (data_directory or root / DATA_FOLDER).resolve()


def image_name(name: str, root: Path, data: Path) -> str:
    """`name` with forward slashes, once it is known to be a path to an image inside `root` and outside `data`."""
    posix = PurePosixPath(name.replace("\\", "/"))
    if not posix.parts or Path(name).anchor or posix.is_absolute() or ".." in posix.parts:
        raise ImageDesignError(
            f"{name!r} cannot name an image. Use a path inside the directory, such as 'logo.png' or "
            "'concepts/cactus.png'.",
            "invalid-name",
            name,
        )
    if (root / posix).resolve().is_relative_to(data):
        raise ImageDesignError(
            f"{name!r} is inside the data directory, {data}, which holds the tool's own files. Choose another name.",
            "invalid-name",
            name,
        )
    if posix.suffix.lower() not in KEPT_SUFFIXES:
        raise ImageDesignError(
            f"{name!r} does not end in an image format the tool makes. End it in one of: {', '.join(KEPT_SUFFIXES)}.",
            "invalid-name",
            name,
        )
    return posix.as_posix()


class Script(NamedTuple):
    """The image.py that builds a drawn SVG, and the lock uv keeps for its dependencies."""

    code: bytes
    lock: bytes | None


@dataclass
class StoredImage:
    """An image's file and the data kept for it, as read from its folder in the data directory."""

    root: Path
    data: Path
    folder: Path
    record: ImageRecord
    versions: ImageVersions
    runs: list[ImageRunRecord]

    @property
    def name(self) -> str:
        return self.record.name

    @property
    def path(self) -> Path:
        return self.root / self.record.name

    def run_folder(self, run_id: str) -> Path:
        return self.folder / "runs" / run_id

    def save_versions(self) -> None:
        write_atomically(self.folder / VERSIONS, self.versions.model_dump_json(indent=2))

    def save_runs(self) -> None:
        write_atomically(self.folder / RUNS, ImageRuns(runs=self.runs).model_dump_json(indent=2))

    def save_record(self) -> None:
        write_atomically(self.folder / RECORD, self.record.model_dump_json(indent=2, exclude_none=True))

    def version(self, version_id: str) -> ImageVersion:
        for version in self.versions.versions:
            if version.id == version_id:
                return version
        known = ", ".join(version.id for version in self.versions.versions) or "none"
        raise ImageDesignError(
            f"Image {self.name} has no version {version_id!r}. Its versions: {known}.", "no-such-version", self.name
        )

    def add_version(
        self, content: bytes, suffix: str, method: ImageMethod, run_id: str | None, script: Script | None = None
    ) -> ImageVersion:
        """Keep `content` as the image's next version, and the script that built it, without touching the image's file."""
        picture = pictures.describe(content)
        if picture is None:
            raise ImageDesignError(
                f"What was made for {self.name} is not an image the tool can read, so it was not kept.",
                "not-an-image",
                self.name,
            )
        number = 1 + max((int(version.id[1:]) for version in self.versions.versions), default=0)
        file = Path("versions") / f"v{number}{suffix}"
        (self.folder / file).parent.mkdir(parents=True, exist_ok=True)
        (self.folder / file).write_bytes(content)
        kept_script: Path | None = None
        if script is not None:
            kept_script = file.with_suffix(".py")
            _write_script(self.folder / kept_script, script)
        version = ImageVersion(
            id=f"v{number}",
            file=file,
            width=picture.width,
            height=picture.height,
            frames=picture.frames,
            sha256=hashlib.sha256(content).hexdigest(),
            method=method,
            run_id=run_id,
            created=datetime.now(UTC),
            script=kept_script,
        )
        self.versions.versions.append(version)
        self.save_versions()
        return version

    def publish(self, version: ImageVersion) -> None:
        """Put `version` in the image's file, and the script that built it, when it has one, in the image's image.py."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(self.path, (self.folder / version.file).read_bytes())
        if version.script is not None:
            _write_script(self.folder / SCRIPT, read_script(self.folder / version.script))
        self.versions.current = version.id
        self.save_versions()

    def keep_hand_changes(self) -> None:
        """Keep the image's file as a version of its own when it is not the version the tool last put there.

        That is a file the tool has not kept yet, such as one put in the directory by hand, or one changed by hand,
        so a change to the image never loses it.
        """
        if not self.path.is_file() or self.current_file_matches():
            return
        version = self.add_version(self.path.read_bytes(), self.path.suffix.lower(), "imported", None)
        self.versions.current = version.id
        self.save_versions()

    def current_file_matches(self) -> bool:
        """Whether the image's file holds the version the tool last put there."""
        if self.versions.current is None or not self.path.is_file():
            return False
        current = self.version(self.versions.current)
        return hashlib.sha256(self.path.read_bytes()).hexdigest() == current.sha256

    def located(self, version: ImageVersion) -> ImageVersion:
        """`version` with the absolute paths of its files."""
        script = self.folder / version.script if version.script is not None else None
        return version.model_copy(update={"file": self.folder / version.file, "script": script})

    def running(self) -> ImageRunRecord | None:
        """The run working on the image, when its process is alive."""
        run = self.runs[-1] if self.runs else None
        return run if run is not None and run.status == "running" and alive(run.pid) else None

    def summary(self) -> ImageSummary:
        last = self.runs[-1] if self.runs else None
        status = last.status if last is not None else None
        if last is not None and status == "running" and not alive(last.pid):
            status = "failed"
        return ImageSummary(
            name=self.name,
            path=self.path,
            current=self.versions.current if self.current_file_matches() else None,
            versions=[self.located(version) for version in self.versions.versions],
            status=status,
        )


def find_image(root: Path, data: Path, name: str) -> StoredImage | None:
    """The image named `name`, ignoring case as Windows and macOS do, when the tool keeps data for it."""
    wanted = name.casefold()
    for folder in _image_folders(data):
        record = _read(folder / RECORD, ImageRecord)
        if record.name.casefold() == wanted:
            return _load(root, data, folder, record)
    return None


def require_image(root: Path, data: Path, name: str) -> StoredImage:
    image = find_image(root, data, image_name(name, root, data))
    if image is None:
        known = ", ".join(image_names(data)) or "none"
        raise ImageDesignError(
            f"There is no image named {name!r} in {root} that the tool keeps data for. The images it does: {known}. "
            "Name one of them, or pass the --directory and --data-directory it was made with.",
            "no-such-image",
            name,
        )
    return image


def new_image(root: Path, data: Path, name: str) -> StoredImage:
    """Start keeping data for the image named `name`."""
    make_data_directory(data)
    record = ImageRecord(id=uuid.uuid4().hex, name=name, created=datetime.now(UTC))
    folder = data / IMAGES / record.id
    folder.mkdir(parents=True)
    image = StoredImage(root=root, data=data, folder=folder, record=record, versions=ImageVersions(), runs=[])
    image.save_versions()
    image.save_runs()
    image.save_record()
    return image


def image_names(data: Path) -> list[str]:
    return sorted(_read(folder / RECORD, ImageRecord).name for folder in _image_folders(data))


def make_data_directory(data: Path) -> None:
    """Make the data directory, with a .gitignore that commits only what a project needs from it."""
    data.mkdir(parents=True, exist_ok=True)
    if not (data / ".gitignore").exists():
        shutil.copyfile(GITIGNORE, data / ".gitignore")


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


# region: Locks


def take_lock(data: Path, name: str, holder: str) -> Path:
    """Claim the image named `name` for `holder`, such as a run, so no other run works on it at the same time.

    The lock is a file only one process can create, so two requests at the same moment cannot both have it. One left
    by a process that has ended is taken over.
    """
    locks = data / LOCKS
    make_data_directory(data)
    locks.mkdir(exist_ok=True)
    path = locks / f"{hashlib.sha256(name.casefold().encode('utf-8')).hexdigest()[:16]}.lock"
    for _ in range(REPLACE_ATTEMPTS):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held_by = _lock_holder(path)
            if held_by is not None:
                raise ImageDesignError(
                    f"Image {name} is already being worked on by {held_by}. Wait for that run to end, or stop it with "
                    f"`image-design cancel-image --name {name}`.",
                    "already-running",
                    name,
                ) from None
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
            json.dump({"pid": os.getpid(), "holder": holder, "name": name}, lock)
        return path
    raise ImageDesignError(f"Could not claim image {name}; another process keeps claiming it. Try again.", None, name)


def release_lock(path: Path, holder: str) -> None:
    """Give up a lock, when `holder` still has it."""
    try:
        claimed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if claimed.get("holder") == holder and claimed.get("pid") == os.getpid():
        path.unlink(missing_ok=True)


def _lock_holder(path: Path) -> str | None:
    """The live process holding a lock, or None when the lock is abandoned."""
    try:
        claimed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # Being written by the process that just made it.
        return "another process" if _age(path) < LOCK_WRITE_SECONDS else None
    pid = claimed.get("pid")
    return f"process {pid}" if isinstance(pid, int) and alive(pid) else None


def _age(path: Path) -> float:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return LOCK_WRITE_SECONDS


# endregion

# region: Files


def read_events(path: Path, offset: int = 0) -> tuple[list[ImageEvent], int]:
    """The events in a run's events.jsonl past `offset`, and the offset to read on from.

    Only whole lines are read, so a line its run is still writing waits for the next read.
    """
    try:
        with path.open("rb") as events:
            events.seek(offset)
            content = events.read()
    except FileNotFoundError:
        return [], offset
    end = content.rfind(b"\n") + 1
    try:
        read = [ImageEvent.model_validate_json(line) for line in content[:end].splitlines() if line.strip()]
    except ValidationError as error:
        raise ImageDesignError(
            f"{path} holds a line that is not an image-design event: {error.errors()[0]['msg']}. Remove that line."
        ) from None
    return read, offset + end


def read_atomically(path: Path) -> str:
    # Windows refuses to open a file in the moment another process replaces it, as write_atomically does.
    for _ in range(REPLACE_ATTEMPTS - 1):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            time.sleep(REPLACE_WAIT_SECONDS)
    return path.read_text(encoding="utf-8")


def write_atomically(path: Path, content: str | bytes) -> None:
    # Written aside and renamed, because other processes read it while this one writes it. Each write has a file of its
    # own to rename, so two at once never take each other's.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
        partial = Path(file.name)
        file.write(content.encode("utf-8") if isinstance(content, str) else content)
    try:
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                partial.replace(path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(REPLACE_WAIT_SECONDS)
    finally:
        partial.unlink(missing_ok=True)


def read_script(path: Path) -> Script:
    """The script at `path` and its lock, which is None when there is none."""
    lock = lock_path(path)
    return Script(path.read_bytes(), lock.read_bytes() if lock.is_file() else None)


def lock_path(script: Path) -> Path:
    return script.with_name(script.name + LOCK_SUFFIX)


def _write_script(path: Path, script: Script) -> None:
    write_atomically(path, script.code)
    lock = lock_path(path)
    if script.lock is None:
        lock.unlink(missing_ok=True)
    else:
        write_atomically(lock, script.lock)


def load_runs(folder: Path) -> list[ImageRunRecord]:
    return _read(folder / RUNS, ImageRuns).runs


def alive(pid: int) -> bool:
    """Whether a process with this id is running."""
    if sys.platform == "win32":
        import ctypes

        # os.kill on Windows terminates the process rather than probing it, so ask the kernel instead.
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _image_folders(data: Path) -> list[Path]:
    return sorted(path.parent for path in (data / IMAGES).glob(f"*/{RECORD}"))


def _load(root: Path, data: Path, folder: Path, record: ImageRecord) -> StoredImage:
    versions = _read(folder / VERSIONS, ImageVersions) if (folder / VERSIONS).is_file() else ImageVersions()
    runs = load_runs(folder) if (folder / RUNS).is_file() else []
    return StoredImage(root=root, data=data, folder=folder, record=record, versions=versions, runs=runs)


def _read[Model: BaseModel](path: Path, model: type[Model]) -> Model:
    try:
        return model.model_validate_json(read_atomically(path))
    except ValidationError as error:
        raise ImageDesignError(
            f"{path} is not an image-design {model.__name__} file: {error.errors()[0]['msg']}. Fix or remove it."
        ) from None


# endregion
