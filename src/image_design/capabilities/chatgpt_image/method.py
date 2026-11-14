"""What generating with ChatGPT takes, and whether Codex, which carries the request, is installed."""

from image_design.capabilities.chatgpt_image import generate
from image_design.intelligence.interface import resolve_agent_provider
from image_design.schemas import (
    DEFAULT_CHATGPT_REASONING_EFFORT,
    DEFAULT_INTELLIGENCE_MODELS,
    INTELLIGENCE_MODELS,
    ChatGPTImageMethod,
    ImageDesignError,
)


def describe() -> ChatGPTImageMethod:
    try:
        resolve_agent_provider("codex")
        problem = None
    except ImageDesignError as error:
        problem = str(error)
    return ChatGPTImageMethod(
        ready=problem is None,
        problem=problem,
        formats=[".png"],
        models=[model for model in INTELLIGENCE_MODELS if model.agent_provider == "codex"],
        default_model=DEFAULT_INTELLIGENCE_MODELS["codex"],
        default_reasoning_effort=DEFAULT_CHATGPT_REASONING_EFFORT,
        max_images=generate.MAX_INPUT_IMAGES,
    )
