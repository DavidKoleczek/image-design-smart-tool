"""What the agent drawing an SVG is told: the templates in prompts/, and the text that fills them."""

from pathlib import Path
from string import Template

from image_design.schemas import Mark, SvgBudgets
from image_design.shared.images import marks as marking

PROMPTS = Path(__file__).parent / "prompts"
# A new session's prompt. Its $request is the request, $work the work folder, $budgets the budgets, $command the build
# command, and $existing, $references, and $marks what the run has besides the request, each empty when it has none.
DRAW = Template((PROMPTS / "draw.md").read_text(encoding="utf-8"))
# A resumed session's prompt, with $state what the work folder holds, and the rest as in DRAW.
RESUME = Template((PROMPTS / "resume.md").read_text(encoding="utf-8"))
# What the agent is told when it finished without building image.py as it is: $report is what the build said.
CHECKED = Template((PROMPTS / "checked.md").read_text(encoding="utf-8"))

# $existing in DRAW and $state in RESUME, for an image whose image.py built the SVG in its file. In these, {current} is
# the render of the image's file, and {svg} a copy of the file.
EDIT = (
    "The work folder holds the drawing as it is: image.py builds image.svg, and {current} is its render (also "
    "attached). Read image.py first and change it rather than starting over."
)
# For an image whose file image.py did not build: changed outside the tool, or committed apart from its version.
UNMATCHED = (
    "image.py may not build the drawing as it is, since its file was changed outside the tool since image.py last "
    "built it. {svg} is the file as it is, and {current} its render (also attached). Make image.py build that drawing, "
    "then make the request's changes."
)
# For an SVG the tool did not draw, which has no image.py yet.
UNSCRIPTED = (
    "There is no image.py yet. {svg} is the drawing as it is, and {current} its render (also attached). Write image.py "
    "so it builds that drawing, then make the request's changes."
)
# $state in RESUME, for a session whose last run did not finish, whose work folder is kept as that run left it.
KEPT = "The work folder is as your last run left it. Build it with the same command as before."
# $state in RESUME, for a new image, or one the session drew before, as RESET's first sentence goes on.
RESET = "The work folder has been set to the image as it is now; build it with the same command as before. "
NEW = "There is no drawing yet."
# $references, heading the references that came with a request or a steering message.
REFERENCES = "References for this request (also attached):"
# $marks, heading the marks of a request or a steering message; {marked} is the render with the marks drawn on it.
MARKED = "{marked} (also attached) is the drawing with marks on it, which show what this request refers to:"
UNMARKED = "Marks on the drawing, which show what this request refers to, as fractions of its width and height:"
UNDER = " Under it: {parts}."
NOTHING_UNDER = " It is over no named part."


def budgets(given: SvgBudgets) -> str:
    """The budgets block: the canvas, and each budget the drawing has."""
    width, height = given.canvas
    lines = [
        "The drawing's budgets, which it should stay within:",
        (
            f'- A canvas of {width} by {height}: width="{width}", height="{height}", and viewBox="0 0 {width} {height}" '
            "on the svg element."
        ),
    ]
    if given.max_shapes is not None:
        lines.append(f"- At most {given.max_shapes:,} shapes: elements that draw, such as path, rect, circle, and use.")
    if given.max_colors is not None:
        lines.append(f"- At most {given.max_colors:,} colors: distinct fill, stroke, and stop colors.")
    if given.max_bytes is not None:
        lines.append(f"- At most {given.max_bytes:,} bytes of SVG.")
    return "\n".join(lines)


def references(paths: list[Path]) -> str:
    if not paths:
        return ""
    return "\n" + "\n".join([REFERENCES, *(f"- {path}" for path in paths)]) + "\n"


def marks(given: list[Mark], marked: Path | None, under: list[list[tuple[str, float]]]) -> str:
    """The marks block: where the marked render is, and each mark with the named parts under it."""
    if not given:
        return ""
    lines = [MARKED.format(marked=marked) if marked is not None else UNMARKED]
    for line, parts, mark in zip(marking.describe(given).splitlines(), under, given, strict=True):
        line = line if line.endswith(".") else line + "."
        if marked is None:
            line += f" Its points: {', '.join(f'({x:.2f}, {y:.2f})' for x, y in mark.points)}."
        elif parts:
            line += UNDER.format(parts=", ".join(f"{part} ({share:.0%} of the mark's area)" for part, share in parts))
        else:
            line += NOTHING_UNDER
        lines.append(line)
    return "\n" + "\n".join(lines) + "\n"


def draw(
    request: str,
    work: Path,
    given_budgets: SvgBudgets,
    command: str,
    existing: str,
    references_block: str,
    marks_block: str,
) -> str:
    return DRAW.substitute(
        request=request,
        work=work,
        budgets=budgets(given_budgets),
        command=command,
        existing=f"\n{existing}\n" if existing else "",
        references=references_block,
        marks=marks_block,
    )


def resume(
    request: str, state: str, changed_budgets: SvgBudgets | None, references_block: str, marks_block: str
) -> str:
    return RESUME.substitute(
        request=request,
        state=state + "\n",
        budgets="\n" + budgets(changed_budgets) + "\n" if changed_budgets is not None else "",
        references=references_block,
        marks=marks_block,
    )


def checked(report: str) -> str:
    return CHECKED.substitute(report=report)
