"""The OpenAI API key requests are billed to: the environment's, or one saved in the platform's credential store."""

import os

from image_design.schemas import ImageDesignError, OpenAIKeyStatus

KEY_VARIABLE = "OPENAI_API_KEY"
# What the saved key is filed under in the credential store.
SERVICE = "image-design"
ENTRY = "openai-api-key"
NO_STORE = (
    "This machine has no credential store the tool can keep the key in. Set the key in the "
    f"{KEY_VARIABLE} environment variable instead."
)


def find() -> str | None:
    """The key to send requests with: the environment's when it has one, else the saved one."""
    return os.environ.get(KEY_VARIABLE) or _saved()


def status() -> OpenAIKeyStatus:
    """Where the key requests are sent with comes from, without the key itself."""
    saved = _saved() is not None
    source = "environment" if os.environ.get(KEY_VARIABLE) else "saved" if saved else None
    return OpenAIKeyStatus(source=source, saved=saved)


def save(key: str) -> None:
    """Keep `key` in the platform's credential store, replacing the one kept before."""
    key = key.strip()
    if not key or any(character.isspace() for character in key):
        raise ImageDesignError(
            "That is not an API key: a key is one run of characters with no spaces. Copy it again from "
            "https://platform.openai.com/api-keys.",
            "bad-key",
        )
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        raise ImageDesignError(NO_STORE, "no-credential-store") from None
    try:
        keyring.set_password(SERVICE, ENTRY, key)
        # A store that takes a key without keeping it would leave the person thinking it was saved.
        kept = keyring.get_password(SERVICE, ENTRY) == key
    except KeyringError:
        kept = False
    if not kept:
        raise ImageDesignError(NO_STORE, "no-credential-store")


def clear() -> None:
    """Forget the saved key, if there is one."""
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return
    try:
        if keyring.get_password(SERVICE, ENTRY) is not None:
            keyring.delete_password(SERVICE, ENTRY)
    except KeyringError as error:
        raise ImageDesignError(
            f"The saved key could not be removed from the credential store: {error}. Remove the entry "
            f"{SERVICE!r} there by hand."
        ) from None


def _saved() -> str | None:
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return None
    try:
        return keyring.get_password(SERVICE, ENTRY) or None
    except KeyringError:
        return None
