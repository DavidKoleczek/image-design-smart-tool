"""Measuring an SVG drawing: what it holds, its named parts, what resvg does not render, and what lies under marks."""

from collections import Counter
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
import re
from typing import NamedTuple
import xml.etree.ElementTree as ElementTree

from PIL import Image, ImageChops, ImageColor, ImageDraw

from image_design.schemas import ImageDesignError, Mark, SvgPart
from image_design.shared.images import pictures

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
XLINK_HREF = f"{{{XLINK_NAMESPACE}}}href"
# The elements that draw.
SHAPES = frozenset({"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "image", "use"})
# The elements whose content is drawn only where something else refers to it, so a group in one is not a part.
NOT_DRAWN = frozenset({"defs", "clipPath", "mask", "pattern", "marker", "symbol"})
# What resvg does not render: the unsupported elements and attributes of
# https://github.com/linebender/resvg/blob/main/docs/unsupported.md, and scripts, animation, and foreignObject, which
# are outside the static SVG it renders.
UNSUPPORTED_ELEMENTS = frozenset(
    {
        "altGlyph",
        "altGlyphDef",
        "altGlyphItem",
        "font",
        "font-face",
        "font-face-format",
        "font-face-name",
        "font-face-src",
        "font-face-uri",
        "glyph",
        "glyphRef",
        "hkern",
        "missing-glyph",
        "vkern",
        "color-profile",
        "script",
        "animate",
        "animateColor",
        "animateMotion",
        "animateTransform",
        "set",
        "foreignObject",
    }
)
UNSUPPORTED_ATTRIBUTES = frozenset(
    {
        "clip",
        "color-interpolation",
        "color-profile",
        "color-rendering",
        "direction",
        "font-size-adjust",
        "font-stretch",
        "glyph-orientation-horizontal",
        "glyph-orientation-vertical",
        "kerning",
        "unicode-bidi",
    }
)
COLOR_PROPERTIES = ("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color")
COLOR_DECLARATION = re.compile(rf"(?<![\w-])({'|'.join(COLOR_PROPERTIES)})\s*:\s*([^;}}]+)")
NOT_COLORS = frozenset({"", "none", "transparent", "currentcolor", "inherit", "initial", "unset", "context-fill"})
LENGTH = re.compile(r"\s*([0-9]*\.?[0-9]+(?:e[-+]?[0-9]+)?)\s*(px)?\s*", re.IGNORECASE)
# Which parts are under a mark is worked out on a render this size along its longer edge, which is plenty to tell
# parts apart and quick to make once per part.
PARTS_EDGE = 256
# A part is under a mark when it fills at least this share of the mark's area, so a sliver along its edge is not.
MIN_SHARE = 0.02
# A channel that changes by less than this when a part is hidden is antialiasing, not the part.
CHANGED = 8


class Measure(NamedTuple):
    """What an SVG holds, before it is set against any budget."""

    size: tuple[float, float] | None
    view_box: tuple[float, float, float, float] | None
    shapes: int
    colors: list[str]
    bytes: int
    texts: int
    parts: list[SvgPart]
    skipped: list[str]


def measure(content: bytes) -> Measure:
    """What the SVG `content` holds, raising when it is not an SVG."""
    root = parse(content)
    counts: Counter[str] = Counter()
    colors: set[str] = set()
    for element in root.iter():
        name = local(element.tag)
        if name in UNSUPPORTED_ELEMENTS:
            counts[f"<{name}>"] += 1
        if name == "use" and _href(element) and not _href(element).startswith("#"):
            counts["<use> of another file"] += 1
        for attribute, value in element.attrib.items():
            if local(attribute) in UNSUPPORTED_ATTRIBUTES:
                counts[f"the {local(attribute)} attribute"] += 1
            if local(attribute) in COLOR_PROPERTIES:
                colors.update(_colors([value]))
        declarations = element.get("style", "") + ((element.text or "") if name == "style" else "")
        colors.update(_colors(value for _, value in COLOR_DECLARATION.findall(declarations)))
    return Measure(
        size=_size(root),
        view_box=_view_box(root),
        shapes=sum(1 for element in root.iter() if local(element.tag) in SHAPES),
        colors=sorted(colors),
        bytes=len(content),
        texts=sum(1 for element in root.iter() if local(element.tag) == "text"),
        parts=[SvgPart(id=part, shapes=_shapes(group)) for part, group in named_parts(root)],
        skipped=[f"{what} ({count})" for what, count in sorted(counts.items())],
    )


def parts_under(content: bytes, marks: list[Mark], resources: Path | None) -> list[list[tuple[str, float]]]:
    """For each mark, the named parts under it and the share of the mark's area each fills, largest first.

    A part's area is where the render changes when the part is hidden, so it is what shows of the part, whatever its
    transforms and whatever is drawn over it.
    """
    root = parse(content)
    parts = named_parts(root)
    if not marks or not parts:
        return [[] for _ in marks]
    with Image.open(BytesIO(pictures.svg_png(content, resources))) as full:
        zoom = min(1.0, PARTS_EDGE / max(full.width, full.height))
    base = _render(root, resources, zoom)
    regions = [_region(mark, base.width, base.height) for mark in marks]
    areas = [region.histogram()[255] for region in regions]
    found: list[list[tuple[str, float]]] = [[] for _ in marks]
    for part, element in parts:
        shown = element.get("display")
        element.set("display", "none")
        try:
            hidden = _render(root, resources, zoom)
        finally:
            if shown is None:
                del element.attrib["display"]
            else:
                element.set("display", shown)
        changed = _changed(base, hidden)
        for index, region in enumerate(regions):
            overlap = ImageChops.logical_and(changed, region).histogram()[255]
            if areas[index] and overlap / areas[index] >= MIN_SHARE:
                found[index].append((part, overlap / areas[index]))
    return [sorted(each, key=lambda item: -item[1]) for each in found]


def parse(content: bytes) -> ElementTree.Element:
    """The SVG's root element, raising when `content` is not an SVG."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ImageDesignError(f"The SVG is not well-formed XML: {error}. Fix it.") from None
    if local(root.tag) != "svg":
        raise ImageDesignError(f"The file's root element is <{local(root.tag)}>, not <svg>. Make it an SVG.")
    return root


def named_parts(root: ElementTree.Element) -> list[tuple[str, ElementTree.Element]]:
    """Each group with an id, named by its id after those of the named groups it is in, in document order."""
    found: list[tuple[str, ElementTree.Element]] = []

    def walk(element: ElementTree.Element, within: str) -> None:
        for child in element:
            name = local(child.tag)
            if name in NOT_DRAWN:
                continue
            path = within
            if name == "g" and child.get("id"):
                path = f"{within}/{child.get('id')}" if within else str(child.get("id"))
                found.append((path, child))
            walk(child, path)

    walk(root, "")
    return found


def local(tag: str) -> str:
    """An element's or attribute's name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _href(element: ElementTree.Element) -> str:
    return element.get("href") or element.get(XLINK_HREF) or ""


def _shapes(element: ElementTree.Element) -> int:
    return sum(1 for each in element.iter() if local(each.tag) in SHAPES)


def _colors(values: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for value in values:
        typed = value.strip().lower()
        if typed in NOT_COLORS or typed.startswith(("url(", "var(")):
            continue
        try:
            rgb = ImageColor.getrgb(typed)
        except ValueError:
            continue
        hexed = "#" + "".join(f"{channel:02x}" for channel in rgb[:3])
        found.add(hexed + f"{rgb[3]:02x}" if len(rgb) == 4 and rgb[3] < 255 else hexed)
    return found


def _size(root: ElementTree.Element) -> tuple[float, float] | None:
    width, height = _length(root.get("width")), _length(root.get("height"))
    return (width, height) if width is not None and height is not None else None


def _length(typed: str | None) -> float | None:
    """A length in pixels, or None for none or one in another unit."""
    if typed is None or (match := LENGTH.fullmatch(typed)) is None:
        return None
    return float(match[1])


def _view_box(root: ElementTree.Element) -> tuple[float, float, float, float] | None:
    numbers = re.split(r"[\s,]+", (root.get("viewBox") or "").strip())
    try:
        x, y, width, height = (float(number) for number in numbers)
    except ValueError:
        return None
    return x, y, width, height


def _render(root: ElementTree.Element, resources: Path | None, zoom: float) -> Image.Image:
    # Written back with SVG's own namespace as the default, as resvg needs, rather than one ElementTree makes up.
    ElementTree.register_namespace("", SVG_NAMESPACE)
    ElementTree.register_namespace("xlink", XLINK_NAMESPACE)
    content = ElementTree.tostring(root, encoding="utf-8")
    with Image.open(BytesIO(pictures.svg_png(content, resources, zoom))) as rendered:
        return rendered.convert("RGBA")


def _changed(base: Image.Image, hidden: Image.Image) -> Image.Image:
    """Where two renders differ, as a 1-bit mask."""
    difference = ImageChops.difference(base, hidden).split()
    widest = difference[0]
    for channel in difference[1:]:
        widest = ImageChops.lighter(widest, channel)
    return widest.point(lambda value: 255 if value >= CHANGED else 0).convert("1")


def _region(mark: Mark, width: int, height: int) -> Image.Image:
    """The area a mark covers, as a 1-bit mask: inside a circle or box, around an arrow's head, along a sketch."""
    region = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(region)
    points = [(x * (width - 1), y * (height - 1)) for x, y in mark.points]
    reach = max(3, round(min(width, height) * 0.05))
    match mark.shape:
        case "circle" | "box":
            (first_x, first_y), (second_x, second_y) = points
            box = (min(first_x, second_x), min(first_y, second_y), max(first_x, second_x), max(first_y, second_y))
            if mark.shape == "circle":
                draw.ellipse(box, fill=255)
            else:
                draw.rectangle(box, fill=255)
        case "arrow":
            head_x, head_y = points[-1]
            draw.ellipse((head_x - reach, head_y - reach, head_x + reach, head_y + reach), fill=255)
        case "sketch":
            if len(points) >= 3:
                draw.polygon(points, fill=255)
            draw.line(points, fill=255, width=reach)
    return region
