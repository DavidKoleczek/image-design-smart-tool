import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/icon";
import { useThumb } from "@/lib/references";
import { cn } from "@/lib/utils";

/**
 * A small preview of a reference: the copy made here for an upload, or the server's for a file it offers. The
 * server's is read once the preview first comes into view, so a folder of hundreds asks only for those scrolled to.
 */
export function ReferenceThumb({
  reference,
  className,
}: {
  reference: { path: string | null; thumb?: string | null };
  className?: string;
}) {
  const box = useRef<HTMLSpanElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const element = box.current;
    if (seen || !element) {
      return;
    }
    const watcher = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setSeen(true);
      }
    });
    watcher.observe(element);
    return () => watcher.disconnect();
  }, [seen]);
  const read = useThumb(reference.thumb || !seen ? null : reference.path);
  const url = reference.thumb ?? read.url;
  return (
    <span
      ref={box}
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
