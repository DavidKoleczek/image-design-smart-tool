"""Marks: drawn on a transparent layer the size of the image they mark, or on a copy of it, and described in words."""

from io import BytesIO
import math

from PIL import Image, ImageColor, ImageDraw, ImageFont

from image_design.schemas import ImageDesignError, Mark

# The shapes drawn from two points; a sketch takes as many as it has.
TWO_POINT_SHAPES = ("circle", "box", "arrow")
# A mark's number is on a badge this many of its lines tall, in a font this share of the badge, as the app draws it.
BADGE = 6
BADGE_FONT = 0.62
# The app's ink for a number on a badge too light for white to read on, such as yellow.
DARK_INK = (18, 22, 28)


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
    # After every line, so one mark's line never hides another's number.
    for number, mark in enumerate(marks, 1):
        if mark.numbered:
            _number(draw, mark, number, width, height, stroke)
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
    """One line per mark, numbered as the marks are given, saying so when its number is drawn, with its note."""
    lines = []
    for number, mark in enumerate(marks, 1):
        what = f"Mark {number} is a {mark.color} {mark.shape}"
        if mark.numbered:
            what += f" with a {number} beside it"
        lines.append(f"- {what}: {mark.note}" if mark.note else f"- {what}.")
    return "\n".join(lines)


def _number(draw: ImageDraw.ImageDraw, mark: Mark, number: int, width: int, height: int, stroke: int) -> None:
    """The mark's number, on a badge of its color."""
    color = ImageColor.getrgb(mark.color)
    side = stroke * BADGE
    font = ImageFont.load_default(round(side * BADGE_FONT))
    text = str(number)
    left, _, right, _ = draw.textbbox((0, 0), text, font=font, anchor="mm")
    across = max(side, right - left + side / 2)
    x, y = _badge_corner(mark, width, height, across, side)
    draw.rounded_rectangle((x, y, x + across, y + side), radius=side / 9, fill=color)
    red, green, blue = color[:3]
    ink = DARK_INK if 0.299 * red + 0.587 * green + 0.114 * blue > 150 else (255, 255, 255)
    draw.text((x + across / 2, y + side / 2), text, fill=ink, font=font, anchor="mm")


def _badge_corner(mark: Mark, width: int, height: int, across: float, side: float) -> tuple[float, float]:
    """The top left of the mark's number badge, `across` by `side`, on the image.

    It goes above a box or a sketch, flush with its left edge, or just inside its top where the image leaves no room
    above; off a circle's upper left; and beyond an arrow's tail, away from what the arrow points at. The app's
    `badgeCorner` places it the same way.
    """
    points = _placed(mark.points, width, height)
    match mark.shape:
        case "arrow":
            (tail_x, tail_y), (head_x, head_y) = points
            back = math.atan2(tail_y - head_y, tail_x - head_x)
            reach = math.hypot(across, side) / 2
            x = tail_x + reach * math.cos(back) - across / 2
            y = tail_y + reach * math.sin(back) - side / 2
        case "circle":
            left, top, right, bottom = _box(points)
            # Its bottom right corner on the outline, halfway round from the circle's top to its left.
            x = (left + right) / 2 - (right - left) / 2 * math.sqrt(0.5) - across
            y = (top + bottom) / 2 - (bottom - top) / 2 * math.sqrt(0.5) - side
        case _:
            every = [*points, *(point for more in mark.strokes for point in _placed(more, width, height))]
            x = min(point_x for point_x, _ in every)
            top = min(point_y for _, point_y in every)
            y = top - side if top >= side else top
    return max(0, min(x, width - across)), max(0, min(y, height - side))


def _placed(points: list[tuple[float, float]], width: int, height: int) -> list[tuple[float, float]]:
    return [(x * (width - 1), y * (height - 1)) for x, y in points]


def _box(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    (first_x, first_y), (second_x, second_y) = points
    return min(first_x, second_x), min(first_y, second_y), max(first_x, second_x), max(first_y, second_y)
