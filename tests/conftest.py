from pathlib import Path
import sys

from fake_openai import FakeImagesAPI
import pytest

from image_design.capabilities.openai_image import images_api as images_api_module
from image_design.shared.images import runs


@pytest.fixture(autouse=True)
def config_directory(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The per-user config location every test sees, so none reads or writes the app settings of whoever runs it."""
    config = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("APPDATA", str(config))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    if sys.platform == "darwin":
        monkeypatch.setenv("HOME", str(config))
    return config


@pytest.fixture
def images_api(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> FakeImagesAPI:
    """The Images API faked, in a working directory of its own, so images land in a fresh .image-design."""
    fake = FakeImagesAPI()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(images_api_module, "client", fake.client)
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)
    monkeypatch.chdir(tmp_path_factory.mktemp("work"))
    return fake
