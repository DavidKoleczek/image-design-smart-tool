from collections.abc import Iterator
from pathlib import Path
import sys

from fake_openai import FakeImagesAPI
import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
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


class MemoryKeyring(KeyringBackend):
    """A credential store that lasts as long as a test."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.kept: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.kept.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.kept[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.kept:
            raise PasswordDeleteError(username)
        del self.kept[(service, username)]


@pytest.fixture(autouse=True)
def no_credential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test, and no process a test starts, reads or writes the credential store of whoever runs it."""
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")


@pytest.fixture
def credential_store() -> Iterator[MemoryKeyring]:
    """A credential store of the test's own, in place of the one that keeps nothing."""
    before = keyring.get_keyring()
    store = MemoryKeyring()
    keyring.set_keyring(store)
    yield store
    keyring.set_keyring(before)


@pytest.fixture
def images_api(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> FakeImagesAPI:
    """The Images API faked, in a working directory of its own, so images land in a fresh .image-design."""
    fake = FakeImagesAPI()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(images_api_module, "client", fake.client)
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)
    monkeypatch.chdir(tmp_path_factory.mktemp("work"))
    return fake
