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
    ImageMethodSetup,
    IntelligenceChoice,
    OpenAIImageMethod,
)
from image_design.shared.images.requests import invalid


def describe(openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod, preferred: list[str]) -> DesignImageMethod:
    """The agent's method, with `preferred`, the config's image models, put first among those it can be given."""
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
    order = image_models(preferred, openai)
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
        image_models=order,
        default_image_model=_first(order, None, openai, chatgpt),
    )


def image_models(preferred: list[str], openai: OpenAIImageMethod) -> list[str]:
    """Every image model the agent can be given, in the order one is picked when none is: those of `preferred` it can
    be given, then the rest in the tool's own order, which starts with the default OpenAI image model."""
    offered = [openai.default_model, *(model.id for model in openai.models), CHATGPT_IMAGE_MODEL]
    # A model named in the config that the tool no longer offers is passed over, so an upgrade does not break it.
    return list(dict.fromkeys([*(model for model in preferred if model in offered), *offered]))


def image_model(
    wanted: str | None, name: str, openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod, preferred: list[str]
) -> str:
    """What the agent makes the image named `name` with: `wanted`, else the first in the order `preferred` sets whose
    method is set up and makes that image. Raises when it is not an image model the agent can be given, its method is
    not set up, or it cannot make that image."""
    picked = wanted or _first(image_models(preferred, openai), name, openai, chatgpt)
    offered = [model.id for model in openai.models]
    if picked != CHATGPT_IMAGE_MODEL and picked not in offered:
        raise invalid(
            f"{picked!r} is not an image model the agent can be given. Pass one of: "
            f"{', '.join([*offered, CHATGPT_IMAGE_MODEL])}.",
            name,
        )
    command, method = _method(picked, openai, chatgpt)
    if not method.ready:
        raise ImageDesignError(
            f"The agent would make its images with {picked} through {command}, which is not set up. {method.problem}",
            "not-set-up",
            name,
        )
    suffix = _suffix(name)
    # Any other name is left to design_image, which says what it takes.
    if suffix in IMAGE_FORMATS and suffix not in method.formats:
        raise invalid(
            f"{command} makes only {', '.join(method.formats)} images, so it cannot make {name}. Name one of those, "
            "or give the agent an OpenAI image model.",
            name,
        )
    return picked


def _first(order: list[str], name: str | None, openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod) -> str:
    """The first of `order` whose method is set up and makes the image named `name`, any image when it is None. Else
    the first set up, or the first of all, so the request then says why it cannot be made."""
    suffix = _suffix(name) if name is not None else None
    ready = [model for model in order if _method(model, openai, chatgpt)[1].ready]
    makes = [
        model for model in ready if suffix not in IMAGE_FORMATS or suffix in _method(model, openai, chatgpt)[1].formats
    ]
    return (makes or ready or order)[0]


def _method(model: str, openai: OpenAIImageMethod, chatgpt: ChatGPTImageMethod) -> tuple[str, ImageMethodSetup]:
    return ("generate-chatgpt-image", chatgpt) if model == CHATGPT_IMAGE_MODEL else ("generate-openai-image", openai)


def _suffix(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).suffix.lower()
