"""The process a detached `generate_openai_image` run runs in; see shared/images/detach.py."""

from image_design.capabilities.openai_image import generate
from image_design.shared.images import detach


def main() -> int:
    return detach.serve(lambda request: generate.start(generate.OpenAIImageRequest.model_validate_json(request)))


if __name__ == "__main__":
    raise SystemExit(main())
