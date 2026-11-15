import { useState, type ReactNode } from "react";

import { MarkChip } from "@/components/activity/Message";
import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Tooltip } from "@/components/ui/tooltip";
import type { Mark } from "@/lib/marks";
import type { Reference } from "@/lib/references";
import { cn } from "@/lib/utils";

/**
 * Where a message to an agent is written: the marks and references that go with it as chips, the text, and under it
 * what the message is sent with. Enter sends, and image files dropped on it become references.
 */
export function Composer({
  label,
  placeholder,
  value,
  onChange,
  marks,
  references,
  onRemoveMark,
  onRemoveReference,
  onAttach,
  onFiles,
  onSend,
  sending,
  blocked,
  sendLabel,
  children,
}: {
  /** What the text field is for, read out for it. */
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  marks: Mark[];
  references: Reference[];
  onRemoveMark: (id: number) => void;
  onRemoveReference: (id: string) => void;
  /** Open what references are picked from. */
  onAttach: () => void;
  /** Image files dropped on the box. */
  onFiles: (transfer: DataTransfer) => void;
  onSend: () => void;
  sending: boolean;
  /** Why the message cannot be sent now; null when it can. */
  blocked: string | null;
  sendLabel: string;
  /** What the message is sent with, between Attach and Send. */
  children?: ReactNode;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        onFiles(event.dataTransfer);
      }}
      className={cn(
        "flex flex-col gap-2 rounded-md border border-line-control bg-field p-2 focus-within:border-ink focus-within:bg-panel",
        over && "outline-1 outline-offset-2 outline-accent-ink outline-dashed",
      )}
    >
      {(marks.length > 0 || references.length > 0) && (
        <div className="flex flex-wrap gap-1">
          {marks.map((mark) => (
            <MarkChip
              key={mark.id}
              chip={{
                kind: "mark",
                number: mark.id,
                color: mark.color,
                shape: mark.shape,
              }}
            >
              <button
                type="button"
                aria-label={`Remove mark ${mark.id}`}
                onClick={() => onRemoveMark(mark.id)}
                className="-mr-1 grid size-4 shrink-0 cursor-default place-items-center rounded-sm text-ink-muted hover:bg-hover hover:text-ink focus-visible:focus-ring focus-visible:outline-none"
              >
                <Icon name="close" />
              </button>
            </MarkChip>
          ))}
          {references.map((reference) => (
            <span
              key={reference.id}
              className="inline-flex h-6 max-w-full items-center gap-1.5 rounded-sm border border-line bg-panel pr-1 pl-0.5"
            >
              <ReferenceThumb reference={reference} className="size-4.5" />
              <span
                title={reference.name}
                className="max-w-32 truncate mono-annotation"
              >
                {reference.name}
              </span>
              {reference.state === "uploading" && <LoadingMark size={12} />}
              {reference.state === "failed" && (
                <Icon name="warning" className="text-danger" />
              )}
              <button
                type="button"
                aria-label={`Remove ${reference.name}`}
                onClick={() => onRemoveReference(reference.id)}
                className="grid size-4 shrink-0 cursor-default place-items-center rounded-sm text-ink-muted hover:bg-hover hover:text-ink focus-visible:focus-ring focus-visible:outline-none"
              >
                <Icon name="close" />
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSend();
          }
        }}
        placeholder={placeholder}
        className="block field-sizing-content max-h-60 min-h-12 w-full resize-none bg-transparent text-body text-ink outline-none placeholder:text-ink-muted"
      />
      <div className="flex items-center gap-1">
        <Tooltip content="Add references" side="top">
          <Button
            size="sm"
            icon
            variant="ghost"
            aria-label="Add references"
            onClick={onAttach}
          >
            <Icon name="attach" />
          </Button>
        </Tooltip>
        {children}
        <span className="flex-1" />
        <span title={blocked ?? undefined}>
          <Button
            variant="primary"
            size="sm"
            icon
            aria-label={sendLabel}
            disabled={blocked !== null || sending}
            onClick={onSend}
          >
            {sending ? <LoadingMark /> : <Icon name="send" />}
          </Button>
        </span>
      </div>
    </div>
  );
}
