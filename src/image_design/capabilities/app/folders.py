"""Asking the person for files, a folder, where to save, or a secret, in a window of their own machine apart from the
app's view, and showing them a file in their file manager."""

import json
from pathlib import Path
import subprocess
import sys

from image_design.schemas import ImageDesignError

# Python's own Tk, run apart from the server: it shows the platform's native dialog on Windows and macOS, and a process
# of its own gives Tk the main thread macOS requires. The hidden window it hangs from stays on top, so the dialog shows
# above the browser that asked for it.
CHOOSE_SCRIPT = """
import json
import sys
import tkinter
from tkinter import filedialog

directory, title, kind, name = sys.argv[1:5]
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
if kind == "folder":
    chosen = filedialog.askdirectory(parent=root, initialdir=directory, title=title, mustexist=True)
    print(json.dumps([chosen] if chosen else []))
elif kind == "save":
    suffix = name[name.rfind("."):]
    chosen = filedialog.asksaveasfilename(
        parent=root,
        initialdir=directory,
        initialfile=name,
        title=title,
        defaultextension=suffix,
        filetypes=[(suffix[1:].upper(), "*" + suffix)],
    )
    print(json.dumps([chosen] if chosen else []))
else:
    print(json.dumps(list(filedialog.askopenfilenames(parent=root, initialdir=directory, title=title))))
"""


# A secret is typed here and not in the app's view, whose calls pass through whatever host shows the app.
SECRET_SCRIPT = """
import json
import sys
import tkinter
from tkinter import ttk

title, label = sys.argv[1:3]
root = tkinter.Tk()
root.title(title)
root.resizable(False, False)
root.attributes("-topmost", True)
value = tkinter.StringVar()
answer = {"value": None}


def accept(event=None):
    answer["value"] = value.get()
    root.destroy()


def cancel(event=None):
    root.destroy()


frame = ttk.Frame(root, padding=16)
frame.grid()
ttk.Label(frame, text=label, wraplength=380, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
entry = ttk.Entry(frame, textvariable=value, show="*", width=56)
entry.grid(row=1, column=0, columnspan=2, pady=(8, 12), sticky="we")
ttk.Button(frame, text="Cancel", command=cancel).grid(row=2, column=0, sticky="e", padx=(0, 8))
ttk.Button(frame, text="Save", command=accept).grid(row=2, column=1, sticky="e")
frame.columnconfigure(0, weight=1)
root.bind("<Return>", accept)
root.bind("<Escape>", cancel)
root.protocol("WM_DELETE_WINDOW", cancel)
root.update_idletasks()
left = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
top = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
root.geometry(f"+{left}+{top}")
entry.focus_force()
root.mainloop()
print(json.dumps(answer))
"""


def ask_secret(title: str, label: str) -> str | None:
    """Ask the person to type a secret into a window on this machine, its characters hidden; None when they cancel.

    It reaches this process over a pipe from the window's own, and is in no argument, file, or log.
    """
    answer = json.loads(_run(SECRET_SCRIPT, [title, label], "set it in the environment instead") or "{}")
    value = (answer.get("value") or "").strip()
    return value or None


def choose_files(directory: Path, title: str) -> list[Path]:
    """Ask the person for files in their platform's file dialog, opened at `directory`; none when they cancel."""
    if not directory.is_dir():
        raise ImageDesignError(f"{directory} is not a folder on this machine. Unpin it and pin the folder again.")
    return _ask(directory, title, "files")


def choose_folder(directory: Path, title: str) -> Path | None:
    """Ask the person for a folder in their platform's folder dialog, opened at `directory`; None when they cancel."""
    chosen = _ask(directory, title, "folder")
    return chosen[0] if chosen else None


def choose_save_path(directory: Path, title: str, name: str) -> Path | None:
    """Ask the person where to save a file in their platform's save dialog, opened at `directory` with `name` filled
    in; None when they cancel."""
    answer = _run(CHOOSE_SCRIPT, [str(directory), title, "save", name], "export it with the CLI instead")
    chosen = json.loads(answer or "[]")
    return Path(chosen[0]) if chosen else None


def show_in_file_manager(path: Path) -> None:
    """Show `path` in the platform's file manager: a folder opened, and a file selected in the folder it is in, where
    the file manager can select one."""
    folder = path.is_dir()
    try:
        if sys.platform == "win32":
            # Explorer takes `/select,` and the path as one argument, which a list of arguments would quote apart.
            subprocess.Popen(f'explorer "{path}"' if folder else f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)] if folder else ["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path if folder else path.parent)])
    except OSError as error:
        raise ImageDesignError(f"Could not open the file manager: {error}. Open {path} in it yourself.") from None


def _ask(directory: Path, title: str, kind: str) -> list[Path]:
    answer = _run(CHOOSE_SCRIPT, [str(directory), title, kind, ""], "drop or paste the images onto the app instead")
    return [Path(path) for path in json.loads(answer or "[]")]


def _run(script: str, arguments: list[str], instead: str) -> str:
    """What `script` prints once the person has answered its window. `instead` says what to do when it cannot show."""
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-c", script, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise ImageDesignError(f"Could not show a window to ask in: {error}. To go on, {instead}.") from None
    if done.returncode != 0:
        reason = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else f"exit code {done.returncode}"
        raise ImageDesignError(
            f"Could not show a window to ask in: {reason}. It needs Tk in the Python running the app. To go on, "
            f"{instead}."
        )
    return done.stdout
