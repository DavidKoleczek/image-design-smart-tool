"""A stand-in for the OpenAI Images API: the real client, with its requests answered in this process."""

import asyncio
import base64
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from io import BytesIO
import json
from typing import Any

import httpx2
from openai import AsyncOpenAI
from PIL import Image

TEXT_TOKENS = 100
IMAGE_TOKENS = 1000
OUTPUT_TOKENS = 800
COLORS = ("#e63946", "#457b9d", "#2a9d8f", "#f4a261", "#8338ec", "#ffbe0b")


@dataclass
class SentRequest:
    """One request as the API received it."""

    path: str
    fields: dict[str, Any]
    files: dict[str, list[bytes]] = field(default_factory=dict)


@dataclass
class FakeImagesAPI:
    """Answers each request with plain images of the size asked for, or as told: refusing, failing, or never."""

    status: int = 200
    error: str = "Invalid size."
    hang: bool = False
    requests: list[SentRequest] = field(default_factory=list)

    def client(self, timeout_seconds: int) -> AsyncOpenAI:
        transport = httpx2.MockTransport(self._answer)
        return AsyncOpenAI(
            api_key="test-key",
            base_url="https://images.test/v1",
            max_retries=0,
            timeout=timeout_seconds,
            http_client=httpx2.AsyncClient(transport=transport),
        )

    async def _answer(self, request: httpx2.Request) -> httpx2.Response:
        sent = _parse(request)
        self.requests.append(sent)
        if self.hang:
            await asyncio.Event().wait()
        if self.status != 200:
            body = {"error": {"message": self.error, "type": "invalid_request_error", "param": "size", "code": None}}
            return httpx2.Response(self.status, json=body)
        fields = sent.fields
        output_format = str(fields.get("output_format", "png"))
        width, height = self._size(sent, output_format)
        images = [
            picture(width, height, COLORS[(len(self.requests) + index) % len(COLORS)], output_format, fields)
            for index in range(int(fields.get("n", 1)))
        ]
        usage = {
            "input_tokens": TEXT_TOKENS + IMAGE_TOKENS * len(sent.files.get("image[]", [])),
            "input_tokens_details": {
                "text_tokens": TEXT_TOKENS,
                "image_tokens": IMAGE_TOKENS * len(sent.files.get("image[]", [])),
            },
            "output_tokens": OUTPUT_TOKENS,
            "total_tokens": 0,
        }
        if str(fields.get("stream", "")).lower() != "true":
            data = [{"b64_json": base64.b64encode(image).decode()} for image in images]
            return httpx2.Response(200, json={"created": 0, "data": data, "usage": usage})
        kind = "image_edit" if sent.path.endswith("/edits") else "image_generation"
        events = []
        for index in range(int(fields.get("partial_images", 0))):
            preview = picture(width, height, COLORS[index], output_format, fields)
            events.append(
                {"type": f"{kind}.partial_image", "b64_json": _encoded(preview), "partial_image_index": index}
            )
        events.append({"type": f"{kind}.completed", "b64_json": _encoded(images[0]), "usage": usage})
        stream = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=stream.encode())

    def _size(self, sent: SentRequest, output_format: str) -> tuple[int, int]:
        size = str(sent.fields.get("size", "auto"))
        if size != "auto":
            width, height = size.split("x")
            return int(width), int(height)
        if output_format == "gif":
            return 512, 512
        if sent.files.get("image[]"):
            with Image.open(BytesIO(sent.files["image[]"][0])) as first:
                return first.size
        return 1024, 1024


def picture(
    width: int, height: int, color: str, output_format: str = "png", fields: dict[str, Any] | None = None
) -> bytes:
    """A plain image, or for a GIF one frame per color, in the format asked for."""
    buffer = BytesIO()
    if output_format == "gif":
        count = int((fields or {}).get("frame_count", 3))
        frames = [Image.new("RGB", (width, height), COLORS[index % len(COLORS)]) for index in range(count)]
        duration = int((fields or {}).get("frame_duration_ms", 200))
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=duration, loop=0)
    else:
        Image.new("RGB", (width, height), color).save(
            buffer, format={"jpeg": "JPEG", "webp": "WEBP"}.get(output_format, "PNG")
        )
    return buffer.getvalue()


def _encoded(content: bytes) -> str:
    return base64.b64encode(content).decode()


def _parse(request: httpx2.Request) -> SentRequest:
    path = request.url.path
    kind = request.headers.get("content-type", "")
    if kind.startswith("application/json"):
        return SentRequest(path, json.loads(request.content))
    message = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {kind}\r\n\r\n".encode() + request.content)
    sent = SentRequest(path, {})
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        content = part.get_payload(decode=True)
        assert isinstance(name, str)
        assert isinstance(content, bytes)
        if part.get_param("filename", header="content-disposition") is None:
            sent.fields[name] = content.decode()
        else:
            sent.files.setdefault(name, []).append(content)
    return sent
