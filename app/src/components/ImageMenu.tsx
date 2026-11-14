import { useRef, useState, type FormEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import {
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
} from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { deleteImage, moveImage } from "@/lib/api";
import { describe } from "@/lib/errors";
import { baseName } from "@/lib/tree";

/** What can be done to an image from its menu, each by its name. */
export type ImageActions = {
  onRename: (name: string) => void;
  onDelete: (name: string) => void;
  /** Start a new image with this one as its first reference. */
  onUseInNew: (name: string) => void;
  /** Add this image to the references of the request being written. */
  onAddReference: (name: string) => void;
  /** The image that request edits, which cannot be a reference to itself; none for a new image. */
  source: string | null;
};

/** What the image menu holds, for menus that list it among other things. */
export function ImageMenuItems({
  name,
  onRename,
  onDelete,
  onUseInNew,
  onAddReference,
  source,
}: ImageActions & { name: string }) {
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

/** The button on an image that opens what can be done to it. */
export function ImageMenu({
  name,
  className,
  ...actions
}: ImageActions & { name: string; className?: string }) {
  return (
    <Menu>
      <MenuTrigger
        render={
          <Button
            size="sm"
            icon
            aria-label={`More for ${name}`}
            className={className}
          />
        }
      >
        <Icon name="more" />
      </MenuTrigger>
      <MenuContent align="end">
        <ImageMenuItems name={name} {...actions} />
      </MenuContent>
    </Menu>
  );
}

/** The last name that was not null, so a dialog keeps what it shows while it closes. */
function useLast(name: string | null): string | null {
  const [last, setLast] = useState(name);
  if (name !== null && name !== last) {
    setLast(name);
  }
  return name ?? last;
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

/** Asks before an image and everything kept for it is deleted. */
export function DeleteDialog({
  name,
  onClose,
  onDeleted,
}: {
  /** The image to delete; the dialog is closed while null. */
  name: string | null;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const shown = useLast(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ name: string; text: string } | null>(
    null,
  );
  const cancel = useRef<HTMLButtonElement>(null);

  const remove = async () => {
    if (name === null || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteImage(name);
      onDeleted();
      onClose();
    } catch (cause) {
      setError({ name, text: describe(cause) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={name !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        title="Delete this image?"
        subtitle={shown}
        initialFocus={cancel}
        className="sm:max-w-110"
      >
        <div className="px-5 pt-4 pb-5">
          <p>
            Its file and every version kept for it are deleted. This cannot be
            undone.
          </p>
          {error && error.name === shown && (
            <Notice className="mt-3">{error.text}</Notice>
          )}
        </div>
        <DialogFooter className="justify-end">
          <Button ref={cancel} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => void remove()}
          >
            {busy ? "Deleting" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
