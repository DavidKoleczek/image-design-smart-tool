"""What the image's agent takes, and whether it can run: an agent provider installed to run it, and a method set up
to make the images it calls for."""

from pathlib import PurePosixPath

from image_design.intelligence.interface import installed, resolve_agent_provider
from image_design.schemas import (
    AGENT_PROVIDERS,
    CHATGPT_IMAGE_MODEL,
    DEFAULT_INTELLIGENCE_MODELS,
    DEFAULT_REASONING_EFFORT,
    IMAGE_FORMATS,
    INTELLIGENCE_MODELS,
    ChatGPTImageMethod,
    DesignImageMethod,
    ImageDesignError,
    IntelligenceChoice,
    OpenAIImageMethod,
)
from image_design.shared.images.requests import invalid


def describe(openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod) -> DesignImageMethod:
    # Without one installed, the default names the first, which is the one a request would ask to be installed.
    provider = AGENT_PROVIDERS[0]
    try:
        provider = resolve_agent_provider()
        problem = None
    except ImageDesignError as error:
        problem = str(error)
    if problem is None and not openai.ready and not chatgpt.ready:
        problem = (
            "The agent makes its images with generate-openai-image or generate-chatgpt-image, and neither is set up. "
            f"{openai.problem} {chatgpt.problem}"
        )
    return DesignImageMethod(
        ready=problem is None,
        problem=problem,
        formats=list(IMAGE_FORMATS),
        models=[model for model in INTELLIGENCE_MODELS if installed(model.agent_provider)],
        default=IntelligenceChoice(
            agent_provider=provider,
            model=DEFAULT_INTELLIGENCE_MODELS[provider],
            reasoning_effort=DEFAULT_REASONING_EFFORT,
        ),
        default_image_model=_default_image_model(openai, chatgpt),
    )


def image_model(wanted: str | None, name: str, openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod) -> str:
    """What the agent makes the image named `name` with: `wanted`, else the default of the first method set up. Raises
    when it is not an image model the agent can be given, its method is not set up, or it cannot make that image."""
    picked = wanted or _default_image_model(openai, chatgpt)
    offered = [model.id for model in openai.models]
    if picked != CHATGPT_IMAGE_MODEL and picked not in offered:
        raise invalid(
            f"{picked!r} is not an image model the agent can be given. Pass one of: "
            f"{', '.join([*offered, CHATGPT_IMAGE_MODEL])}.",
            name,
        )
    command, method = (
        ("generate-chatgpt-image", chatgpt) if picked == CHATGPT_IMAGE_MODEL else ("generate-openai-image", openai)
    )
    if not method.ready:
        raise ImageDesignError(
            f"The agent would make its images with {picked} through {command}, which is not set up. {method.problem}",
            "not-set-up",
            name,
        )
    suffix = PurePosixPath(name.replace("\\", "/")).suffix.lower()
    # Any other name is left to design_image, which says what it takes.
    if suffix in IMAGE_FORMATS and suffix not in method.formats:
        raise invalid(
            f"{command} makes only {', '.join(method.formats)} images, so it cannot make {name}. Name one of those, "
            "or give the agent an OpenAI image model.",
            name,
        )
    return picked


def _default_image_model(openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod) -> str:
    return openai.default_model if openai.ready or not chatgpt.ready else CHATGPT_IMAGE_MODEL
