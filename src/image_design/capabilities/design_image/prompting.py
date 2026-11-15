"""What the image's agent is told: the templates in prompts/, and the text that fills them."""

from pathlib import Path
from string import Template

from image_design.capabilities.design_image import tooling
from image_design.capabilities.design_image.told import argument
from image_design.core.skill import skill
from image_design.schemas import CHATGPT_IMAGE_MODEL, Mark
from image_design.shared.images import marks as marking

PROMPTS = Path(__file__).parent / "prompts"
# A new session's prompt. Its $request is the request; $told the image's history; $target the lines under the
# workflow's first step of the image it is for; $tool the command it makes images with and $command that command's
# name; $given the end of the second step, with the lines under it of what came with the request; $directory the
# image's work directory and $directories the flags of an image directory that is not the default; $skills the craft
# skills whose text is $guidelines; and $tool_help the command's help. $told and $directories are empty when there is
# nothing to say.
NEW = Template((PROMPTS / "new.md").read_text(encoding="utf-8"))
# A resumed session's prompt, with $told what happened since its last turn, $guidelines the editing skill, $tool_guide
# empty or SWITCHED, and the rest as in NEW. $tool is said again each turn, since the person can pick another image
# model between turns.
RESUME = Template((PROMPTS / "resume.md").read_text(encoding="utf-8"))
# $tool_guide in RESUME when the person picked another image model than the session's last turn made images with, since
# the help and the prompting skill the session has are for the other command. Its $guidelines is the prompting skill,
# and the rest is as in NEW.
SWITCHED = Template((PROMPTS / "switched.md").read_text(encoding="utf-8"))

# The craft skills given in full: how to prompt each command's image model, and how to edit. Editing is one skill for
# every image model, since what differs between them is in their prompting skills; it would split into one per image
# model once their editing advice differs.
OPENAI_PROMPTING = "prompting-openai-images"
CHATGPT_PROMPTING = "prompting-chatgpt-images"
EDITING = "editing-images"
CREATE = "The name of the image the user has asked you to create is {name}."
EDIT = "The image is {name}, at {path}. {state}"
FILE = "The person is looking at its file, which is attached."
VERSION = "The person is looking at {version}, kept at {shown}, which is attached."
FRAME = "It is an animation, and the person means frame {frame}, counting from 0. `--frame` takes it."
MARKED = (
    "{marked} (also attached) is that version with marks the person drew on it, which show what the request refers "
    "to. {file} holds the marks, which `--marks` takes:"
)
MASK = "{mask} is a mask the person drew, transparent where changes may go. `--mask` takes it."
GIVEN_REFERENCES = "References the person gave with the request:"
PICKED = "The user picked these parameters for you to use:"
SIZE_PICKED = "size: {width}x{height} (`--size {width}x{height}`)"
QUALITY_PICKED = "quality: {quality} (`--quality {quality}`)"
# How the second step ends: with what came with the request under it, or without when nothing did.
GIVEN = " The user picked this method/model and the following parameters:"
NOTHING_GIVEN = " The user picked this method/model."
OPENAI_TOOL = "`image-design generate-openai-image --model {model}`"
CHATGPT_TOOL = "`image-design generate-chatgpt-image`"
OPENAI_COMMAND = "generate-openai-image"
CHATGPT_COMMAND = "generate-chatgpt-image"
DIRECTORIES = " The images are not in the default directory, so pass {flags} to each `image-design` command."
# Where a line of the list under the workflow's first step starts, and where the lines under it do.
ITEM = "   - "
UNDER = "     "
# The skill's directory goes with it, since a skill names its files relative to it.
GUIDELINES = '<guidelines skill="{name}" directory="{directory}">\n{text}\n</guidelines>'
ONE_SKILL = "{names} skill"
SKILLS = "{names} skills"


def target(
    name: str, path: Path, state: str, version: str | None, looking_at: Path | None, frame: int | None
) -> list[str]:
    """What the request is for: the image as it is and the version the person is looking at, which is `looking_at`,
    or the name of one to create when there is none."""
    if looking_at is None:
        return [CREATE.format(name=name)]
    items = [
        EDIT.format(name=name, path=path, state=state),
        FILE if looking_at == path else VERSION.format(version=version, shown=looking_at),
    ]
    return items + ([FRAME.format(frame=frame)] if frame is not None else [])


def given(
    marks: list[Mark], marked: Path | None, marks_file: Path | None, mask: Path | None, references: list[Path]
) -> list[str]:
    """What came with the request: the marks, the mask, and the references, each as a file the agent can pass on."""
    items: list[str] = []
    if marks and marked is not None and marks_file is not None:
        lines = [line if line.endswith(".") else line + "." for line in marking.describe(marks).splitlines()]
        items.append("\n".join([MARKED.format(marked=marked, file=marks_file), *lines]))
    if mask is not None:
        items.append(MASK.format(mask=mask))
    if references:
        items.append("\n".join([GIVEN_REFERENCES, *(f"{number}. {path}" for number, path in enumerate(references, 1))]))
    return items


def picked(size: tuple[int, int] | None, quality: str | None) -> list[str]:
    """What the person picked for the image's calls in the app, each with the flag that passes it on."""
    parts: list[str] = []
    if size is not None:
        parts.append(SIZE_PICKED.format(width=size[0], height=size[1]))
    if quality is not None:
        parts.append(QUALITY_PICKED.format(quality=quality))
    return ["\n".join([PICKED, *(f"- {part}" for part in parts)])] if parts else []


def directories(root: Path, data: Path, default_root: Path, default_data: Path) -> str:
    """How every command names the image directory, when the defaults from the agent's working directory are not it."""
    flags = []
    if root != default_root:
        flags.append(f"--directory {argument(str(root))}")
    if data != default_data:
        flags.append(f"--data-directory {argument(str(data))}")
    if not flags:
        return ""
    return DIRECTORIES.format(flags=" ".join(f"`{flag}`" for flag in flags))


def steered(message: str, items: list[str]) -> str:
    """A steering message, followed by what came with it."""
    return message + "".join(f"\n\n{item}" for item in items)


def tool(image_model: str) -> str:
    """The command the agent makes its images with, for the image model the person picked."""
    return CHATGPT_TOOL if image_model == CHATGPT_IMAGE_MODEL else OPENAI_TOOL.format(model=image_model)


def command(image_model: str) -> str:
    return CHATGPT_COMMAND if image_model == CHATGPT_IMAGE_MODEL else OPENAI_COMMAND


def prompting_skill(image_model: str) -> str:
    """The craft skill on prompting the image model the agent makes its images with."""
    return CHATGPT_PROMPTING if image_model == CHATGPT_IMAGE_MODEL else OPENAI_PROMPTING


def named(skills: list[str]) -> str:
    names = " and ".join(f"`{name}`" for name in skills)
    return (SKILLS if len(skills) > 1 else ONE_SKILL).format(names=names)


def guidelines(skills: list[str]) -> str:
    """The text of each craft skill, as the prompt gives it in place of the agent loading it."""
    return "\n\n".join(
        GUIDELINES.format(name=name, directory=tooling.CRAFT / name, text=tooling.craft_skill(name)) for name in skills
    )


def given_block(given_items: list[str]) -> str:
    """The end of the workflow's second step: what came with the request, as lines under it."""
    return GIVEN + "\n" + listed(given_items) if given_items else NOTHING_GIVEN


def listed(items: list[str]) -> str:
    """`items` as lines of the list under the workflow's first step, with the lines of each under it."""
    lines: list[str] = []
    for item in items:
        first, *rest = item.splitlines()
        lines += [ITEM + first, *(UNDER + line for line in rest)]
    return "\n".join(lines)


def new(
    request: str,
    target_items: list[str],
    given_items: list[str],
    directory: Path,
    directories_line: str,
    image_model: str,
    editing: bool,
    told_block: str,
) -> str:
    # A new session that edits an image is given how to edit too, as a resumed one is.
    skills = [prompting_skill(image_model), *([EDITING] if editing else [])]
    return NEW.substitute(
        request=request,
        told="\n" + told_block if told_block else "",
        target=listed(target_items),
        given=given_block(given_items),
        tool=tool(image_model),
        command=command(image_model),
        directory=str(directory),
        directories=directories_line,
        skills=named(skills),
        tool_help=skill(command(image_model)),
        guidelines=guidelines(skills),
    )


def resume(
    request: str,
    target_items: list[str],
    given_items: list[str],
    image_model: str,
    switched: bool,
    told_block: str,
) -> str:
    tool_guide = ""
    if switched:
        skills = [prompting_skill(image_model)]
        tool_guide = "\n" + SWITCHED.substitute(
            command=command(image_model),
            skills=named(skills),
            tool_help=skill(command(image_model)),
            guidelines=guidelines(skills),
        )
    return RESUME.substitute(
        request=request,
        told="\n" + told_block if told_block else "",
        target=listed(target_items),
        given=given_block(given_items),
        tool=tool(image_model),
        tool_guide=tool_guide,
        guidelines=guidelines([EDITING]),
    )
