import { useRef, useState, type FormEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { MenuItem, MenuSeparator } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { moveImage } from "@/lib/api";
import { describe } from "@/lib/errors";
import { remove } from "@/lib/organize";
import { baseName } from "@/lib/paths";
import type { Entry } from "@/lib/tree";

/** What can be done to an image from its menu, each by its name. */
export type ImageActions = {
  onDelete: (name: string) => void;
  /** Start a new image with this one as its first reference. */
  onUseInNew: (name: string) => void;
  /** Add this image to the references of the request being written. */
  onAddReference: (name: string) => void;
  /** The image that request edits, which cannot be a reference to itself; none for a new image. */
  source: string | null;
};

/** The ways an image goes into a request, for a menu about the image. */
export function ReferenceItems({
  name,
  onUseInNew,
  onAddReference,
  source,
}: Omit<ImageActions, "onDelete"> & { name: string }) {
  return (
    <>
      <MenuItem onClick={() => onUseInNew(name)}>
        <Icon name="add" />
        Use in a new image
      </MenuItem>
      <MenuItem disabled={name === source} onClick={() => onAddReference(name)}>
        <Icon name="attach" />
        Add as a reference
      </MenuItem>
    </>
  );
}

/**
 * What the image menu holds where the images show as a list with no folders, so renaming an image and moving it are
 * one thing, asked for in a dialog.
 */
export function ImageMenuItems({
  name,
  onRename,
  onDelete,
  ...references
}: ImageActions & { name: string; onRename: (name: string) => void }) {
  return (
    <>
      <ReferenceItems name={name} {...references} />
      <MenuSeparator />
      <MenuItem onClick={() => onRename(name)}>
        <Icon name="rename" />
        Rename or move
      </MenuItem>
      <MenuSeparator />
      <MenuItem onClick={() => onDelete(name)} className="text-danger">
        <Icon name="delete" />
        Delete
      </MenuItem>
    </>
  );
}

/** The last value that was not null, so a dialog keeps what it shows while it closes. */
function useLast<Value>(value: Value | null): Value | null {
  const [last, setLast] = useState(value);
  if (value !== null && value !== last) {
    setLast(value);
  }
  return value ?? last;
}

function RenameForm({
  name,
  input,
  onClose,
  onRenamed,
}: {
  name: string;
  input: RefObject<HTMLInputElement | null>;
  onClose: () => void;
  onRenamed: (name: string) => void;
}) {
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = useRef(false);
  const unchanged = value.trim() === name || value.trim() === "";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (unchanged || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const moved = await moveImage(name, value.trim());
      onRenamed(moved.name);
      onClose();
    } catch (cause) {
      setError(describe(cause));
      setBusy(false);
    }
  };

  // The name alone starts selected, so typing replaces it and leaves the folder and the extension.
  const selectName = () => {
    if (selected.current || !input.current) {
      return;
    }
    selected.current = true;
    const base = baseName(name);
    const start = name.length - base.length;
    const dot = base.lastIndexOf(".");
    input.current.setSelectionRange(
      start,
      start + (dot > 0 ? dot : base.length),
    );
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="contents">
      <div className="px-5 pt-4 pb-5">
        <Label htmlFor="image-name">Name</Label>
        <Input
          id="image-name"
          ref={input}
          onFocus={selectName}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={error !== null}
          className="mono-value"
        />
        {error && <Notice className="mt-3">{error}</Notice>}
      </div>
      <DialogFooter className="justify-end">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={unchanged || busy}>
          {busy ? "Renaming" : "Rename"}
        </Button>
      </DialogFooter>
    </form>
  );
}

/** Asks for an image's new name, which is its path in the directory, so a folder in it moves the image there. */
export function RenameDialog({
  name,
  onClose,
  onRenamed,
}: {
  /** The image to rename; the dialog is closed while null. */
  name: string | null;
  onClose: () => void;
  onRenamed: (name: string) => void;
}) {
  const shown = useLast(name);
  const input = useRef<HTMLInputElement>(null);
  return (
    <Dialog open={name !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        title="Rename or move"
        subtitle={shown}
        initialFocus={input}
        className="sm:max-w-110"
      >
        {shown !== null && (
          <RenameForm
            key={shown}
            name={shown}
            input={input}
            onClose={onClose}
            onRenamed={onRenamed}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function counted(count: number, one: string): string {
  return `${count} ${one}${count === 1 ? "" : "s"}`;
}

const KEPT =
  "every version, every run, and for a drawing its script and the conversations with its agent";

/** What a delete of the entries is asked as: by name for one, and by how many of each for several. */
function asked(entries: Entry[]): {
  title: string;
  subtitle: string | null;
  text: string;
} {
  const folders = entries.filter((entry) => entry.folder).length;
  const images = entries.length - folders;
  if (entries.length === 1) {
    return folders === 1
      ? {
          title: "Delete this folder?",
          subtitle: entries[0].path,
          text: `Every image in it is deleted, with everything kept for each: ${KEPT}.`,
        }
      : {
          title: "Delete this image?",
          subtitle: entries[0].path,
          text: `Its file and everything kept for it are deleted: ${KEPT}.`,
        };
  }
  const what = [
    ...(images > 0 ? [counted(images, "image")] : []),
    ...(folders > 0 ? [counted(folders, "folder")] : []),
  ].join(" and ");
  return {
    title: `Delete ${what}?`,
    subtitle: null,
    text: `Every image${folders > 0 ? ", and every image in a folder," : ""} is deleted, with everything kept for each: ${KEPT}.`,
  };
}

/**
 * Asks before images and folders are deleted, with everything kept for each image. Once confirmed they go from the
 * view at once, and any that could not be deleted come back.
 */
export function DeleteDialog({
  entries,
  onClose,
}: {
  /** What to delete, none of it inside a folder that is also here; the dialog is closed while null. */
  entries: Entry[] | null;
  onClose: () => void;
}) {
  const shown = useLast(entries);
  const cancel = useRef<HTMLButtonElement>(null);
  const { title, subtitle, text } = asked(shown ?? []);

  return (
    <Dialog open={entries !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        title={title}
        subtitle={subtitle}
        initialFocus={cancel}
        className="sm:max-w-110"
      >
        <p className="px-5 pt-4 pb-5">{text} This cannot be undone.</p>
        <DialogFooter className="justify-end">
          <Button ref={cancel} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              for (const entry of entries ?? []) {
                remove(entry.path, entry.folder);
              }
              onClose();
            }}
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
