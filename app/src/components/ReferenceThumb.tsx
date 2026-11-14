import { Icon } from "@/components/ui/icon";
import { useThumb } from "@/lib/references";
import { cn } from "@/lib/utils";

/** A small preview of a reference: the copy made here for an upload, or the server's for a file it offers. */
export function ReferenceThumb({
  reference,
  className,
}: {
  reference: { path: string | null; thumb?: string | null };
  className?: string;
}) {
  const read = useThumb(reference.thumb ? null : reference.path);
  const url = reference.thumb ?? read.url;
  return (
    <span
      className={cn(
        "relative grid shrink-0 place-items-center overflow-hidden rounded-sm border border-line bg-field text-ink-faint",
        className,
      )}
    >
      {url ? (
        <img
          src={url}
          alt=""
          draggable={false}
          className="block size-full checker object-cover"
        />
      ) : (
        read.error && <Icon name="warning" />
      )}
    </span>
  );
}
