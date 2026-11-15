import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { BESIDE, numbered, ROLE_ICONS, ROLE_LABELS } from "@/lib/calls";
import { methodLabel, usageLabel } from "@/lib/format";
import { fileName } from "@/lib/references";
import type { ImageCall } from "@/lib/thread";
import { between, timeOfDay } from "@/lib/time";

/**
 * An image call in full, as it was recorded: the images in the order they were sent, what each was sent as, the
 * parameters, and the whole prompt.
 */
export function CallDialog({
  call,
  label,
  onClose,
  onEdit,
}: {
  /** The call to show; null while the dialog is closed. */
  call: ImageCall | null;
  /** What a model is called, by its id. */
  label: (model: string) => string;
  onClose: () => void;
  /** Open the call in the editor, to send it again as it is or changed. */
  onEdit: (call: ImageCall) => void;
}) {
  const images = call ? numbered(call.images) : [];
  const used = call ? usageLabel(call.usage) : null;
  return (
    <Dialog open={call !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        title="Image call"
        subtitle={
          call && (
            <span className="flex gap-3">
              <span>{methodLabel(call.method)}</span>
              <span>{call.edits ? "edit" : "create"}</span>
              <span className="truncate">{call.name}</span>
              <span>{call.state}</span>
            </span>
          )
        }
        className="sm:max-w-200"
      >
        {call && (
          <div className="grid min-h-0 flex-1 overflow-y-auto sm:grid-cols-[21rem_1fr]">
            <div className="flex flex-col gap-2 bg-canvas py-4 pr-4 pl-5">
              <h3 className="text-label">Images</h3>
              {images.length === 0 && (
                <p className="text-caption text-ink-muted">None</p>
              )}
              {images.map((image, index) => (
                <div key={index} className="flex min-w-0 items-center gap-2.5">
                  {BESIDE.includes(image.role) ? (
                    <span className="grid size-10 shrink-0 place-items-center rounded-sm border border-line bg-field text-ink-muted">
                      <Icon name={ROLE_ICONS[image.role]} size={20} />
                    </span>
                  ) : (
                    <ReferenceThumb
                      reference={{ path: image.path }}
                      className="size-10"
                    />
                  )}
                  <div className="min-w-0">
                    <div className="truncate mono-value">
                      {fileName(image.path)}
                    </div>
                    <div className="flex gap-2 mono-annotation text-ink-muted">
                      {image.number !== null && (
                        <span>image {image.number}</span>
                      )}
                      <span>{ROLE_LABELS[image.role]}</span>
                    </div>
                  </div>
                </div>
              ))}
              <h3 className="mt-3 text-label">Parameters</h3>
              <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1">
                {[
                  ["model", label(call.model)] as [string, string],
                  ...call.parameters,
                ].map(([name, value]) => (
                  <div key={name} className="contents">
                    <dt className="mono-annotation text-ink-muted">{name}</dt>
                    <dd className="mono-value wrap-break-word">{value}</dd>
                  </div>
                ))}
              </dl>
              <h3 className="mt-3 text-label">Record</h3>
              <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1">
                <div className="contents">
                  <dt className="mono-annotation text-ink-muted">written by</dt>
                  <dd className="mono-value">
                    {call.agent ? "the agent" : call.sender}
                  </dd>
                </div>
                <div className="contents">
                  <dt className="mono-annotation text-ink-muted">sent</dt>
                  <dd className="mono-value">
                    {timeOfDay(call.started)}
                    {call.finished &&
                      call.state === "sent" &&
                      `, took ${between(call.started, call.finished)}`}
                  </dd>
                </div>
                {used && (
                  <div className="contents">
                    <dt className="mono-annotation text-ink-muted">used</dt>
                    <dd className="mono-value">{used}</dd>
                  </div>
                )}
                {call.versions.length > 0 && (
                  <div className="contents">
                    <dt className="mono-annotation text-ink-muted">made</dt>
                    <dd className="mono-value">{call.versions.join(", ")}</dd>
                  </div>
                )}
              </dl>
            </div>
            <div className="flex min-w-0 flex-col gap-2.5 px-5 pt-4 pb-5">
              <h3 className="text-label">Prompt</h3>
              <p className="border-l-2 border-accent-ink py-0.5 pl-2.5 wrap-break-word whitespace-pre-wrap">
                {call.prompt}
              </p>
              {call.error && (
                <p className="wrap-break-word text-danger">{call.error}</p>
              )}
            </div>
          </div>
        )}
        {call && (
          <DialogFooter className="justify-end">
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            {call.state !== "sending" && (
              <Button variant="primary" onClick={() => onEdit(call)}>
                Edit and send again
              </Button>
            )}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
