"""The process a detached run runs in, with the Images API faked: `answer` answers its request, `hang` never does."""

from pathlib import Path
import sys

from fake_openai import FakeImagesAPI
import pytest

from image_design.capabilities.openai_image import background, images_api
from image_design.shared.images import runs


def command(behavior: str) -> list[str]:
    """What runs a detached run with the API faked, in place of `generate.BACKGROUND_COMMAND`."""
    return [sys.executable, str(Path(__file__)), behavior]


if __name__ == "__main__":
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runs, "POLL_SECONDS", 0.01)
        patch.setattr(images_api, "client", FakeImagesAPI(hang=sys.argv[1] == "hang").client)
        code = background.main()
    raise SystemExit(code)
