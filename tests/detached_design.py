"""The process a detached `design_image` run runs in, with its agent faked to say where it was started, and end."""

from pathlib import Path
import sys

from fake_design import fake_designer, says_where_it_runs
import pytest

from image_design.capabilities.design_image import background


def command(state: Path) -> list[str]:
    """What runs a detached `design_image` with its agent faked, in place of `design.BACKGROUND_COMMAND`, with the
    tool's state in `state`."""
    return [sys.executable, str(Path(__file__)), str(state)]


if __name__ == "__main__":
    with pytest.MonkeyPatch.context() as patch:
        fake_designer(patch, Path(sys.argv[1])).behavior = says_where_it_runs
        code = background.main()
    raise SystemExit(code)
