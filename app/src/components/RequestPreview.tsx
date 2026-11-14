import { useEffect, useState } from "react";

import { MarksPicture } from "@/components/Marks";
import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Icon, type IconName } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { Thumb } from "@/components/ui/thumb";
import {
  previewImageRequest,
  type ImageRequest,
  type ImageRequestPreview,
  type ImageSummary,
} from "@/lib/api";
import { describe } from "@/lib/errors";
import { methodLabel } from "@/lib/format";
import type { Mark } from "@/lib/marks";
import { usePicture } from "@/lib/pictures";
import { fileName, type Reference } from "@/lib/references";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

type Sent = ImageRequestPreview["images"][number];

const ROLES: Record<Sent["role"], string> = {
  source: "source",
  "marked-copy": "marked copy",
  reference: "reference",
  marks: "marks layer",
  mask: "mask",
};
const ROLE_ICONS: Record<Sent["role"], IconName> = {
  source: "image",
  "marked-copy": "mark",
  reference: "image",
  marks: "circle",
  mask: "area",
};
// What goes beside the images rather than among them, so it has no number of its own.
const BESIDE: Sent["role"][] = ["marks", "mask"];

function Part({
  from,
  yours = false,
  children,
}: {
  from: string;
  yours?: boolean;
  children: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 border-l-2 py-0.5 pl-2.5",
        yours ? "border-accent-ink" : "border-line",
      )}
    >
      <span className="mono-annotation text-ink-muted">{from}</span>
      <p className="whitespace-pre-wrap">{children}</p>
    </div>
  );
}

type Guides = {
  /** The request's references, in the order it sends them. */
  references: Reference[];
  marks: Mark[];
  /** The mask as it is sent, as a data URL; null for none. */
  mask: string | null;
};

const TILE = "size-10 shrink-0 rounded-sm border border-line";

/** The marks as the request sends them: alone on a layer of their own, or drawn on a copy of the source. */
function MarksTile({
  marks,
  source,
  copy,
}: {
  marks: Mark[];
  source: { image: ImageSummary; shown: Shown };
  /** Whether they are drawn on a copy of the source rather than sent beside it. */
  copy: boolean;
}) {
  const picture = source.shown.picture;
  const { url } = usePicture(
    copy && picture ? { ...picture, small: true } : null,
  );
  return (
    <MarksPicture
      marks={marks}
      width={source.shown.width ?? 1}
      height={source.shown.height ?? 1}
      url={copy ? url : null}
      className={cn(TILE, "checker")}
    />
  );
}

/** What the library worked out the request would send: the images in order, the parameters, and the prompt. */
function Preview({
  preview,
  source,
  references,
  marks,
  mask,
}: Guides & {
  preview: ImageRequestPreview;
  source: { image: ImageSummary; shown: Shown } | null;
}) {
  const numbered = preview.images.filter(
    (image) => !BESIDE.includes(image.role),
  );
  const sent = preview.images.filter((image) => image.role === "reference");
  const written = preview.added
    ? preview.prompt
        .slice(0, preview.prompt.length - preview.added.length)
        .trimEnd()
    : preview.prompt;
  return (
    <div className="grid min-h-0 flex-1 overflow-y-auto sm:grid-cols-[21rem_1fr]">
      <div className="flex flex-col gap-2 bg-canvas py-4 pr-4 pl-5">
        <h3 className="text-label">Images</h3>
        {preview.images.length === 0 && (
          <p className="text-caption text-ink-muted">None</p>
        )}
        {preview.images.map((image, index) => {
          const own = image.role === "source" && source;
          const reference =
            image.role === "reference"
              ? (references[sent.indexOf(image)] ?? null)
              : null;
          const marked =
            (image.role === "marks" || image.role === "marked-copy") && source;
          const name = own
            ? [source.image.name, source.shown.version?.id]
                .filter(Boolean)
                .join(" ")
            : reference
              ? reference.name
              : image.path && image.role !== "mask"
                ? fileName(image.path)
                : ROLES[image.role];
          return (
            <div key={index} className="flex min-w-0 items-center gap-2.5">
              {own ? (
                <Thumb
                  picture={
                    source.shown.picture && {
                      ...source.shown.picture,
                      small: true,
                    }
                  }
                  shape={source.shown}
                  className="size-10"
                />
              ) : reference ? (
                <ReferenceThumb reference={reference} className="size-10" />
              ) : marked ? (
                <MarksTile
                  marks={marks}
                  source={source}
                  copy={image.role === "marked-copy"}
                />
              ) : image.role === "mask" && mask ? (
                <img
                  src={mask}
                  alt=""
                  className={cn(TILE, "checker object-contain")}
                />
              ) : (
                <span className="grid size-10 shrink-0 place-items-center rounded-sm border border-line bg-field text-ink-muted">
                  <Icon name={ROLE_ICONS[image.role]} size={20} />
                </span>
              )}
              <div className="min-w-0">
                <div className="truncate mono-value">{name}</div>
                <div className="flex gap-2 mono-annotation text-ink-muted">
                  {numbered.includes(image) && (
                    <span>image {numbered.indexOf(image) + 1}</span>
                  )}
                  <span>{ROLES[image.role]}</span>
                </div>
              </div>
            </div>
          );
        })}
        <h3 className="mt-3 text-label">Parameters</h3>
        <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1">
          {Object.entries(preview.parameters).map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="mono-annotation text-ink-muted">{name}</dt>
              <dd className="mono-value wrap-break-word">{String(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="flex min-w-0 flex-col gap-2.5 px-5 pt-4 pb-5">
        <h3 className="text-label">Prompt</h3>
        <Part from="Your prompt" yours>
          {written}
        </Part>
        {preview.added && (
          <Part from="Added for the marks">{preview.added}</Part>
        )}
      </div>
    </div>
  );
}

/** Shows what a request would send before it is sent, as the library works it out, with nothing sent or kept. */
export function RequestPreview({
  open,
  request,
  source,
  references,
  marks,
  mask,
  onClose,
  onGenerate,
}: Guides & {
  open: boolean;
  /** The request to preview; null while the dialog is closed. */
  request: ImageRequest | null;
  /** The image the request edits and what of it shows, which stands for the source among the images. */
  source: { image: ImageSummary; shown: Shown } | null;
  onClose: () => void;
  onGenerate: () => void;
}) {
  const [read, setRead] = useState<{
    asked: string;
    preview: ImageRequestPreview | null;
    error: string | null;
  } | null>(null);
  const asked = request ? JSON.stringify(request) : null;

  useEffect(() => {
    if (asked === null) {
      return;
    }
    let current = true;
    previewImageRequest(JSON.parse(asked) as ImageRequest).then(
      (preview) => current && setRead({ asked, preview, error: null }),
      (cause: unknown) =>
        current && setRead({ asked, preview: null, error: describe(cause) }),
    );
    return () => {
      current = false;
    };
  }, [asked]);

  // What was read for another request is not this one's.
  const shown = read && (asked === null || read.asked === asked) ? read : null;
  const preview = shown?.preview ?? null;
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        title="Request preview"
        subtitle={
          preview && (
            <span className="flex gap-3">
              <span>{methodLabel(preview.method)}</span>
              <span>{preview.edits ? "edit" : "create"}</span>
              <span className="truncate">{preview.name}</span>
            </span>
          )
        }
        className="sm:max-w-200"
      >
        {preview ? (
          <Preview
            preview={preview}
            source={source}
            references={references}
            marks={marks}
            mask={mask}
          />
        ) : (
          <div className="grid min-h-40 flex-1 place-items-center p-5">
            {shown?.error ? (
              <Notice>{shown.error}</Notice>
            ) : (
              <LoadingMark size={24} />
            )}
          </div>
        )}
        <DialogFooter className="justify-end">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button variant="primary" disabled={!preview} onClick={onGenerate}>
            Generate
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
