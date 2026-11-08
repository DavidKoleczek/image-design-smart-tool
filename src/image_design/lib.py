from typing import Literal, overload

from image_design.capabilities.intelligence_models import intelligence_models
from image_design.core import manifest
from image_design.core import skill as skill_module
from image_design.schemas import IntelligenceModels, Manifest


def load_manifest() -> Manifest:
    """The tool's manifest as structured data, read from the SMART_TOOL.md shipped inside the package."""
    return manifest.load_manifest()


def skill(capability: str | None = None) -> str:
    """The tool's skill, or the named capability's own skill, wrapped so a reader knows where the tool's files are."""
    return skill_module.skill(capability)


def version() -> str:
    """The installed package's version, from its metadata."""
    return skill_module.version()


@overload
def list_intelligence_models(structured: Literal[False] = False) -> str: ...


@overload
def list_intelligence_models(structured: Literal[True]) -> IntelligenceModels: ...


def list_intelligence_models(structured: bool = False) -> str | IntelligenceModels:
    """The AI models to pick from for an agentic capability.

    The models are those of the installed agent providers; a capability also takes any other model its agent provider
    knows by name.

    Args:
        structured: Return `IntelligenceModels` instead of the text, for code that reads the fields.

    Returns:
        By default, text for an agent to read: the default as the flags to pass, then one model per line.
    """
    listing = intelligence_models.list_intelligence_models()
    return listing if structured else intelligence_models.describe(listing)
