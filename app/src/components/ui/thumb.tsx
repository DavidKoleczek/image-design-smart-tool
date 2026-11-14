import { Icon } from "@/components/ui/icon";
import { usePicture, type Picture } from "@/lib/pictures";
import { cn } from "@/lib/utils";

/**
 * A small preview of an image, over the checkerboard where it is transparent. Sized by its class. It crops the image
 * to its own shape, for previews too small to show a wide image whole, unless given the image's `shape`, which it
 * then shows whole.
 */
export function Thumb({
  picture,
  shape,
  animated = false,
  className,
}: {
  /** Nothing for a file that is not an image the tool can read. */
  picture: Picture | null;
  /** The image's size, to show it whole rather than cropped. */
  shape?: { width: number | null; height: number | null };
  /** Marks an animation, whose preview is its first frame. */
  animated?: boolean;
  className?: string;
}) {
  const { url } = usePicture(picture);
  const width = shape?.width ?? 0;
  const height = shape?.height ?? 0;
  const whole = width > 0 && height > 0;
  return (
    <span
      className={cn(
        "relative grid shrink-0 place-items-center overflow-hidden rounded-sm border border-line bg-field",
        className,
      )}
    >
      {url && (
        <img
          src={url}
          alt=""
          draggable={false}
          style={whole ? { aspectRatio: `${width} / ${height}` } : undefined}
          // The checkerboard is the image's own, so it shows through the image and not around it.
          className={cn(
            "block checker",
            whole
              ? width >= height
                ? "w-full"
                : "h-full"
              : "size-full object-cover",
          )}
        />
      )}
      {animated && (
        <span className="absolute right-0.5 bottom-0.5 grid size-3.5 place-items-center rounded-[2px] bg-ink text-panel">
          <Icon name="play" className="size-2.5" />
        </span>
      )}
    </span>
  );
}
