"""The process a detached `draw_svg_image` run runs in; see shared/images/detach.py."""

from image_design.capabilities.svg_image import draw
from image_design.shared.images import detach


def main() -> int:
    return detach.serve(lambda request: draw.start(draw.SvgImageRequest.model_validate_json(request)))


if __name__ == "__main__":
    raise SystemExit(main())
