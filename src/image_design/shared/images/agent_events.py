"""How a run on an image reports what its agent does: the progress it shows, and the usage it adds up."""

from typing import Any

from image_design.intelligence.schemas import AgentEvent
from image_design.schemas import ImageUsage

# How much of a tool call a run's progress shows; its event's data has the call in full.
SHOWN_CALL_CHARACTERS = 200


def shown(event: AgentEvent) -> str:
    """What a run's progress shows of an agent event: what it said, and the tools it called."""
    match event.kind:
        case "message":
            return event.text
        case "tool_call":
            line = " ".join(event.text.split())
            return line if len(line) <= SHOWN_CALL_CHARACTERS else line[: SHOWN_CALL_CHARACTERS - 3] + "..."
    return ""


def added(usage: ImageUsage | None, data: dict[str, Any]) -> ImageUsage:
    """The run's usage with one more model call's added, its cost known only when the agent provider gives it."""
    total = usage or ImageUsage()
    cost = (data.get("cost") or {}).get("USD")
    return ImageUsage(
        input_text_tokens=total.input_text_tokens + (data.get("input_tokens") or 0),
        output_tokens=total.output_tokens + (data.get("output_tokens") or 0),
        cost=(total.cost or 0) + cost if cost is not None else total.cost,
    )
