import { ImageMenuItems, type ImageActions } from "@/components/ImageMenu";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd } from "@/components/ui/kbd";
import {
  Menu,
  MenuContent,
  MenuGroup,
  MenuGroupLabel,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
} from "@/components/ui/menu";
import { StatusMark } from "@/components/ui/status-mark";
import { Thumb } from "@/components/ui/thumb";
import type { ImageListing, ImageSummary } from "@/lib/api";
import { shortDirectory } from "@/lib/images";
import { filePicture } from "@/lib/pictures";

/** Your images as a menu in the top bar, where there is no room for the pane beside the canvas. */
export function ImageSwitcher({
  listing,
  image,
  onSelect,
  onNew,
  ...actions
}: ImageActions & {
  listing: ImageListing | null;
  /** The image in view; none for a new image, not generated yet. */
  image: ImageSummary | null;
  onSelect: (name: string) => void;
  onNew: () => void;
}) {
  const images = listing?.images ?? [];
  return (
    <Menu>
      <MenuTrigger
        render={
          <Button
            size="sm"
            aria-label={image ? `Image: ${image.name}` : "Pick an image"}
            className="min-w-0 shrink pl-0.5"
          />
        }
      >
        {image ? (
          <Thumb
            picture={filePicture(image, true)}
            className="size-5 rounded-[2px]"
          />
        ) : (
          <Icon name="image" className="ml-1" />
        )}
        <span className="min-w-0 truncate text-body font-medium">
          {image?.name ?? "New image"}
        </span>
        <Icon name="chevron" className="text-ink-muted" />
      </MenuTrigger>
      <MenuContent className="w-75 max-w-[calc(100vw-16px)]">
        <div className="max-h-80 overflow-y-auto">
          {images.map((each) => (
            <MenuItem
              key={each.name}
              onClick={() => onSelect(each.name)}
              className="h-9"
            >
              <Thumb picture={filePicture(each, true)} className="size-6" />
              <span className="min-w-0 flex-1 truncate">{each.name}</span>
              {each.status !== null && each.status !== "done" && (
                <StatusMark status={each.status} />
              )}
              {each.name === image?.name && (
                <Icon name="check" className="text-accent-ink" />
              )}
            </MenuItem>
          ))}
        </div>
        {images.length > 0 && <MenuSeparator />}
        <MenuItem onClick={onNew}>
          <Icon name="add" />
          <span className="flex-1">New image</span>
          <Kbd>N</Kbd>
        </MenuItem>
        {image && (
          <>
            <MenuSeparator />
            <MenuGroup>
              <MenuGroupLabel className="truncate">{image.name}</MenuGroupLabel>
              <ImageMenuItems name={image.name} {...actions} />
            </MenuGroup>
          </>
        )}
        {listing && (
          <>
            <MenuSeparator />
            <p
              title={listing.directory}
              className="flex h-6 items-center truncate px-2 mono-annotation text-ink-muted"
            >
              {shortDirectory(listing.directory)}
            </p>
          </>
        )}
      </MenuContent>
    </Menu>
  );
}
