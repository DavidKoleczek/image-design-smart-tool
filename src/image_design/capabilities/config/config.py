"""The person's defaults for the tool: config.json in their config directory, the same in every directory."""

from pathlib import Path

from pydantic import ValidationError

from image_design.schemas import CHATGPT_IMAGE_MODEL, OPENAI_IMAGE_MODELS, ImageDesignConfig, ImageDesignError
from image_design.shared.images.store import write_atomically
from image_design.shared.state import config_directory

CONFIG = "config.json"


def config_path() -> Path:
    """Where the config is kept, in the platform's per-user config location."""
    return config_directory() / CONFIG


def read_config(path: Path) -> ImageDesignConfig:
    """The config kept at `path`; the tool's defaults when none is. Raises for one that cannot be read, rather than
    going by defaults the person did not set."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ImageDesignConfig()
    except OSError as error:
        raise ImageDesignError(
            f"Could not read the config at {path}: {error}. Check that the file can be read.", "bad-config"
        ) from None
    try:
        return ImageDesignConfig.model_validate_json(text)
    except ValidationError as error:
        problem = error.errors()[0]
        field = ".".join(str(part) for part in problem["loc"]) or "config"
        raise ImageDesignError(
            f"The config at {path} is not valid: {field}: {problem['msg']}. Fix it with `image-design config`, or "
            "delete the file to go back to the tool's defaults.",
            "bad-config",
        ) from None


def update_config(path: Path, design_image_models: list[str] | None) -> ImageDesignConfig:
    """Change what is given in the config at `path`, keep the rest as it is, and return it as kept."""
    config = read_config(path)
    if design_image_models is not None:
        offered = [model.id for model in OPENAI_IMAGE_MODELS] + [CHATGPT_IMAGE_MODEL]
        unknown = [model for model in design_image_models if model not in offered]
        if unknown:
            raise ImageDesignError(
                f"{', '.join(repr(model) for model in unknown)} is not an image model design-image can be given. Name "
                f"some of: {', '.join(offered)}.",
                "bad-config",
            )
        config.design_image_models = list(dict.fromkeys(design_image_models))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(path, config.model_dump_json(indent=2))
    except OSError as error:
        raise ImageDesignError(
            f"Could not save the config to {path}: {error}. Check that the folder can be written.", "bad-config"
        ) from None
    return config
