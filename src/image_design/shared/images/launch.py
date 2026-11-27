"""The first process of a detached run: it starts the command it is given apart from the caller's console, session,
and job, with the same pipes, and exits, so the run descends from nothing a caller's process tree takes down with it.

It imports none of the library, so it starts at once and the library is imported only by the run's own process.
"""

import json
import subprocess
import sys
from typing import IO, Any


def detached_process(
    command: list[str], stdin: int | IO[Any], stdout: int | IO[Any], environment: dict[str, str] | None = None
) -> subprocess.Popen[bytes]:
    """Start `command` apart from this process's console, session, and job, so ending them leaves it running."""
    if sys.platform != "win32":
        return _popen(command, stdin, stdout, environment, start_new_session=True)
    # A console of its own without a window, so it opens none.
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # Out of the caller's job as well, since a host may end everything in its job when it exits.
        return _popen(command, stdin, stdout, environment, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB)
    except PermissionError:
        # The job allows no breaking away. Hosts built on Node let the children of their children leave it anyway.
        return _popen(command, stdin, stdout, environment, creationflags=flags)


def _popen(
    command: list[str],
    stdin: int | IO[Any],
    stdout: int | IO[Any],
    environment: dict[str, str] | None,
    start_new_session: bool = False,
    creationflags: int = 0,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.DEVNULL,
        env=environment,
        start_new_session=start_new_session,
        creationflags=creationflags,
    )


def main() -> int:
    """Start the command named by the arguments with this process's stdin and stdout."""
    try:
        detached_process(sys.argv[1:], sys.stdin, sys.stdout)
    except OSError as error:
        failure = {"error": f"The process that runs the request did not start: {error}", "reason": "start-failed"}
        print(json.dumps(failure), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
