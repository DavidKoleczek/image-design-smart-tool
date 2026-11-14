"""Marks: drawn on a transparent layer the size of the image they mark, or on a copy of it, and described in words."""

from io import BytesIO
import math

from PIL import Image, ImageColor, ImageDraw

from image_design.schemas import ImageDesignError, Mark

# The shapes drawn from two points; a sketch takes as many as it has.
TWO_POINT_SHAPES = ("circle", "box", "arrow")


def require_marks(marks: list[Mark]) -> None:
    """Raise for a mark that cannot be drawn, before a request is sent with it."""
    for number, mark in enumerate(marks, 1):
        if mark.shape in TWO_POINT_SHAPES and len(mark.points) != 2:
            raise ImageDesignError(
                f"Mark {number} is a {mark.shape} with {len(mark.points)} points. A {mark.shape} takes exactly two: "
                + ("its tail, then its head." if mark.shape == "arrow" else "two opposite corners.")
            )
        if mark.shape in TWO_POINT_SHAPES and mark.strokes:
            raise ImageDesignError(
                f"Mark {number} is a {mark.shape} with strokes, which only a sketch has. Leave out its strokes."
            )
        try:
            ImageColor.getrgb(mark.color)
        except ValueError:
            raise ImageDesignError(
                f"Mark {number} has the color {mark.color!r}, which is not a color. Use a CSS color name such as "
                "'red', or a hex code such as '#e63946'."
            ) from None


def layer(marks: list[Mark], width: int, height: int) -> bytes:
    """The marks drawn on a transparent PNG of `width` by `height`."""
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    stroke = max(3, round(min(width, height) / 120))
    for mark in marks:
        color = ImageColor.getrgb(mark.color)
        points = _placed(mark.points, width, height)
        match mark.shape:
            case "circle":
                draw.ellipse(_box(points), outline=color, width=stroke)
            case "box":
                draw.rectangle(_box(points), outline=color, width=stroke)
            case "arrow":
                (tail_x, tail_y), (head_x, head_y) = points
                draw.line(points, fill=color, width=stroke)
                angle = math.atan2(head_y - tail_y, head_x - tail_x)
                length = stroke * 5
                for side in (-1, 1):
                    barb = angle + math.pi + side * math.pi / 6
                    end = (head_x + length * math.cos(barb), head_y + length * math.sin(barb))
                    draw.line([(head_x, head_y), end], fill=color, width=stroke)
            case "sketch":
                for line in (points, *(_placed(more, width, height) for more in mark.strokes)):
                    if len(set(line)) == 1:
                        # A stroke that never moved is a dot, which a line of no length would not draw.
                        (x, y), radius = line[0], stroke / 2
                        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
                    else:
                        draw.line(line, fill=color, width=stroke, joint="curve")
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def drawn(image: bytes, marks: list[Mark]) -> bytes:
    """A PNG of `image` with the marks drawn on it."""
    with Image.open(BytesIO(image)) as original:
        canvas = original.convert("RGBA")
    with Image.open(BytesIO(layer(marks, canvas.width, canvas.height))) as marked:
        canvas.alpha_composite(marked.convert("RGBA"))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def describe(marks: list[Mark]) -> str:
    """One line per mark, numbered as the marks are given, with its note when it has one."""
    lines = []
    for number, mark in enumerate(marks, 1):
        what = f"Mark {number} is a {mark.color} {mark.shape}"
        lines.append(f"- {what}: {mark.note}" if mark.note else f"- {what}.")
    return "\n".join(lines)


def _placed(points: list[tuple[float, float]], width: int, height: int) -> list[tuple[float, float]]:
    return [(x * (width - 1), y * (height - 1)) for x, y in points]


def _box(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    (first_x, first_y), (second_x, second_y) = points
    return min(first_x, second_x), min(first_y, second_y), max(first_x, second_x), max(first_y, second_y)
