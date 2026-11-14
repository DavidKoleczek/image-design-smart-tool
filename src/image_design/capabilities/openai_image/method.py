"""What generating with an OpenAI image model takes, and whether a request can be sent from this machine."""

from typing import get_args

from image_design.capabilities.openai_image import generate, images_api
from image_design.schemas import (
    DEFAULT_OPENAI_IMAGE_MODEL,
    IMAGE_FORMATS,
    OPENAI_IMAGE_MODELS,
    ImageDesignError,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageMethod,
    OpenAIImageQuality,
    OpenAIImageSizes,
)
from image_design.shared.images import pictures


def describe() -> OpenAIImageMethod:
    try:
        images_api.preflight()
        problem = None
    except ImageDesignError as error:
        problem = str(error)
    return OpenAIImageMethod(
        ready=problem is None,
        problem=problem,
        formats=list(IMAGE_FORMATS),
        models=list(OPENAI_IMAGE_MODELS),
        default_model=DEFAULT_OPENAI_IMAGE_MODEL,
        sizes=OpenAIImageSizes(
            step=pictures.SIZE_STEP,
            max_edge=pictures.MAX_EDGE,
            max_ratio=pictures.MAX_RATIO,
            min_pixels=pictures.MIN_PIXELS,
            max_pixels=pictures.MAX_PIXELS,
        ),
        qualities=list(get_args(OpenAIImageQuality)),
        complexities=list(get_args(OpenAIImageComplexity)),
        backgrounds=list(get_args(OpenAIImageBackground)),
        max_images=generate.MAX_INPUT_IMAGES,
        max_count=generate.MAX_COUNT,
        max_previews=generate.MAX_PREVIEWS,
        frames=generate.FRAMES,
        frame_ms=generate.FRAME_MS,
    )
