"""The process a detached `design_image` run runs in; see shared/images/detach.py."""

from image_design.capabilities.design_image import design
from image_design.shared.images import detach


def main() -> int:
    return detach.serve(lambda request: design.start(design.DesignImageRequest.model_validate_json(request)))


if __name__ == "__main__":
    raise SystemExit(main())
