import { Icon } from "@/components/ui/icon";
import { Select } from "@/components/ui/select";
import type { ImageListing } from "@/lib/api";
import { updateDraft } from "@/lib/drafts";
import { byName } from "@/lib/paths";

// The top of the directory, as the folder field holds and shows it, which no folder's path can be.
const TOP = "/";

/**
 * Where a new image goes, beside the tile that stands for it: its name as typed, before the extension its format sets,
 * and the folder of the directory it is made in.
 */
export function NewImageName({
  draftKey,
  listing,
  folder,
  typed,
  extension,
}: {
  /** What the new image's request is kept under. */
  draftKey: string;
  listing: ImageListing | null;
  /** The folder it goes in, "" for the top. */
  folder: string;
  /** Its name as it stands in the field. */
  typed: string;
  extension: string;
}) {
  const folders = [...(listing?.folders ?? [])].sort(byName);
  return (
    <>
      <span className="grid size-11 shrink-0 place-items-center rounded-sm border border-dashed border-line-control text-ink-muted">
        <Icon name="add" size={20} />
      </span>
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <label className="flex h-7 min-w-0 flex-1 items-center gap-0.5 rounded-sm border border-line-control bg-field px-2 focus-within:border-ink focus-within:bg-panel focus-within:focus-ring">
          <input
            aria-label="Name"
            spellCheck={false}
            autoComplete="off"
            value={typed}
            onChange={(event) =>
              updateDraft(draftKey, { name: event.target.value })
            }
            className="min-w-0 flex-1 bg-transparent mono-value text-ink outline-none"
          />
          <span className="mono-value text-ink-muted">{extension}</span>
        </label>
        <Select
          label="Folder"
          value={folder || TOP}
          onChange={(picked) =>
            updateDraft(draftKey, { folder: picked === TOP ? "" : picked })
          }
          items={[
            { value: TOP, label: TOP },
            ...folders.map((each) => ({ value: each, label: each })),
          ]}
          className="w-auto max-w-[45%] shrink-0"
        />
      </div>
    </>
  );
}
