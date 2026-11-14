"""The OpenAI Images API, reached through the openai package. The only module that imports it, since it is an extra."""

import base64
from importlib.util import find_spec
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from image_design.core.skill import DISTRIBUTION, repository_url
from image_design.schemas import (
    ImageDesignError,
    ImageFormat,
    ImageUsage,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageModel,
    OpenAIImageQuality,
)
from image_design.shared.images.runs import RunOutput

if TYPE_CHECKING:
    from openai import AsyncOpenAI

KEY_VARIABLE = "OPENAI_API_KEY"
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_.*-]+")


class ApiRequest(BaseModel):
    """One request to the Images API, with its input images as files already in the run's folder."""

    model: str
    prompt: str
    images: list[Path]
    markup: Path | None = None
    mask: Path | None = None
    size: tuple[int, int] | None = None
    quality: OpenAIImageQuality | None = None
    complexity: OpenAIImageComplexity | None = None
    background: OpenAIImageBackground | None = None
    output_format: ImageFormat
    compression: int | None = None
    count: int = 1
    frames: int | None = None
    frame_ms: int | None = None
    previews: int = 0


def preflight() -> None:
    """Raise naming what to set up when a request cannot be sent from here."""
    if find_spec("openai") is None:
        url = repository_url()
        source = f'"{DISTRIBUTION}[openai] @ git+{url}"' if url else f'"{DISTRIBUTION}[openai]"'
        raise ImageDesignError(
            f"generate_openai_image needs the openai extra. Install image-design with it: `uv tool install {source}`, "
            f"or `uv add {source}` in a project that uses the library.",
            "not-set-up",
        )
    if not os.environ.get(KEY_VARIABLE):
        raise ImageDesignError(
            f"generate_openai_image needs an OpenAI API key in the {KEY_VARIABLE} environment variable. Create one at "
            "https://platform.openai.com/api-keys and set it before running the tool.",
            "not-set-up",
        )


def parameters(request: ApiRequest) -> dict[str, str | int | bool]:
    """What the request sets besides its prompt and images, by the names the Images API gives them. What it leaves
    out is the API's choice."""
    given: dict[str, str | int | None] = {
        "model": request.model,
        "size": f"{request.size[0]}x{request.size[1]}" if request.size else None,
        "quality": request.quality,
        "complexity": request.complexity,
        "background": request.background,
        "output_format": request.output_format,
        "output_compression": request.compression,
        "n": request.count,
        "frame_count": request.frames,
        "frame_duration_ms": request.frame_ms,
        "partial_images": request.previews or None,
    }
    return {name: value for name, value in given.items() if value is not None}


def client(timeout_seconds: int) -> "AsyncOpenAI":
    """The client requests are sent with. Tests replace it with one whose requests never leave the process."""
    from openai import AsyncOpenAI

    # A request is never sent twice, since one that failed or timed out may still have been billed.
    return AsyncOpenAI(max_retries=0, timeout=timeout_seconds)


async def send(request: ApiRequest, model: OpenAIImageModel, timeout_seconds: int, output: RunOutput) -> None:
    """Send `request`, and pass each preview, image, and the usage to `output` as they arrive."""
    import openai

    settings: dict[str, Any] = {"prompt": request.prompt, **parameters(request)}
    try:
        async with client(timeout_seconds) as api:
            images = api.images
            if request.images:
                settings["image"] = [_file(path) for path in request.images]
                settings["markup"] = _file(request.markup) if request.markup else openai.omit
                settings["mask"] = _file(request.mask) if request.mask else openai.omit
                if request.previews:
                    stream = await images.edit(**settings, stream=True)
                    await _receive(stream, model, output)
                    return
                response = await images.edit(**settings)
            else:
                if request.previews:
                    stream = await images.generate(**settings, stream=True)
                    await _receive(stream, model, output)
                    return
                response = await images.generate(**settings)
            for item in response.data or []:
                if item.b64_json:
                    output.image(base64.b64decode(item.b64_json))
            if response.usage is not None:
                output.used(priced(response.usage, model))
    except openai.APIStatusError as error:
        raise ImageDesignError(_refused(error.status_code, error.body, error.message), "refused") from None
    except openai.APITimeoutError:
        raise ImageDesignError(
            "The OpenAI API did not answer in time. The request may still have been billed, so check the image before "
            "you send it again, or give it more time with timeout_seconds (--timeout-seconds).",
            "unreachable",
        ) from None
    except openai.APIConnectionError as error:
        raise ImageDesignError(
            f"Could not reach the OpenAI API: {error.message}. If the request went out, it may still have been billed.",
            "unreachable",
        ) from None
    except openai.APIError as error:
        raise ImageDesignError(_refused(None, error.body, error.message), "refused") from None


async def _receive(stream: Any, model: OpenAIImageModel, output: RunOutput) -> None:
    """Pass on each preview and image of a streamed request as it arrives."""
    async for event in stream:
        if event.type in ("image_generation.partial_image", "image_edit.partial_image"):
            output.preview(base64.b64decode(event.b64_json), event.partial_image_index)
        elif event.type in ("image_generation.completed", "image_edit.completed"):
            output.image(base64.b64decode(event.b64_json))
            output.used(priced(event.usage, model))


def priced(usage: Any, model: OpenAIImageModel) -> ImageUsage:
    """The tokens of a response's usage, and what they cost at the model's prices."""
    text = usage.input_tokens_details.text_tokens
    image = usage.input_tokens_details.image_tokens
    # The model pages give one output price, for image tokens; an image model writes no text.
    cost = (text * model.text_input + image * model.image_input + usage.output_tokens * model.image_output) / 1_000_000
    return ImageUsage(
        input_text_tokens=text, input_image_tokens=image, output_tokens=usage.output_tokens, cost=round(cost, 6)
    )


def _file(path: Path) -> tuple[str, bytes, str]:
    return path.name, path.read_bytes(), MEDIA_TYPES.get(path.suffix.lower(), "image/png")


def _refused(status: int | None, body: object, message: str) -> str:
    detail = body.get("error", body) if isinstance(body, dict) else None
    if isinstance(detail, dict):
        message = str(detail.get("message") or message)
        param = detail.get("param")
    else:
        param = None
    # An error about the key can quote part of it.
    message = KEY_PATTERN.sub("[key]", message)
    about = f", about {param}" if param else ""
    code = f" ({status}{about})" if status else ""
    hint = {
        401: f" Check the key in {KEY_VARIABLE}.",
        403: " Check that the key's project can use this model.",
        429: " Wait and try again, or check the project's usage limits.",
    }.get(status or 0, " Change what it names and try again.")
    return f"The OpenAI API refused the request{code}: {message}{hint}"
