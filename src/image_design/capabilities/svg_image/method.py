"""What drawing an SVG takes, and whether an agent provider is installed to draw it."""

from image_design.capabilities.svg_image.check import EXPORT_FORMATS
from image_design.intelligence.interface import installed, resolve_agent_provider
from image_design.schemas import (
    AGENT_PROVIDERS,
    DEFAULT_INTELLIGENCE_MODELS,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SVG_CANVAS,
    INTELLIGENCE_MODELS,
    SVG_SUFFIX,
    ImageDesignError,
    IntelligenceChoice,
    SvgImageMethod,
)


def describe() -> SvgImageMethod:
    # Without one installed, the default names the first, which is the one a request would ask to be installed.
    provider = AGENT_PROVIDERS[0]
    try:
        provider = resolve_agent_provider()
        problem = None
    except ImageDesignError as error:
        problem = str(error)
    return SvgImageMethod(
        ready=problem is None,
        problem=problem,
        formats=[SVG_SUFFIX],
        models=[model for model in INTELLIGENCE_MODELS if installed(model.agent_provider)],
        default=IntelligenceChoice(
            agent_provider=provider,
            model=DEFAULT_INTELLIGENCE_MODELS[provider],
            reasoning_effort=DEFAULT_REASONING_EFFORT,
        ),
        default_canvas=DEFAULT_SVG_CANVAS,
        export_formats=list(EXPORT_FORMATS),
    )
