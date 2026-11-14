import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Segmented } from "@/components/ui/segmented";
import { Select } from "@/components/ui/select";
import { exportSvgImage, type ImageSummary } from "@/lib/api";
import { describe } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { useMethods } from "@/lib/methods";
import { stem } from "@/lib/request";
import { baseName } from "@/lib/tree";
import type { Shown } from "@/lib/viewed";

const FORMATS: Record<string, string> = {
  ".png": "PNG",
  ".webp": "WebP",
  ".jpg": "JPEG",
};
const SCALES = [1, 2, 4, 8];

/**
 * A raster copy of what shows of a drawing, at a multiple of its canvas. A drawing has no pixel size of its own, so
 * this is a render of the SVG, made without a request and saved where the person says.
 */
export function Export({
  image,
  shown,
}: {
  image: ImageSummary;
  shown: Shown;
}) {
  const { methods } = useMethods();
  const formats = methods?.svg.export_formats ?? Object.keys(FORMATS);
  const [format, setFormat] = useState(formats[0]);
  const [scale, setScale] = useState(2);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const version = !shown.file && shown.version ? shown.version.id : null;

  const save = async () => {
    setBusy(true);
    setSaved(null);
    setError(null);
    try {
      setSaved(
        await exportSvgImage({
          name: image.name,
          ...(version ? { version } : {}),
          format,
          scale,
        }),
      );
    } catch (cause) {
      setError(`Could not export. ${describe(cause)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover
      onOpenChange={() => {
        setSaved(null);
        setError(null);
      }}
    >
      <PopoverTrigger render={<Button size="sm" />}>
        <Icon name="export" />
        Export
      </PopoverTrigger>
      <PopoverContent
        label="Export"
        side="top"
        align="end"
        className="flex w-72 flex-col gap-2.5 p-3"
      >
        <div className="flex items-center gap-2">
          <span className="w-12 shrink-0 text-label text-ink-muted">
            Format
          </span>
          <Segmented<string>
            label="Format"
            size="sm"
            value={format}
            onChange={setFormat}
            options={formats.map((each) => ({
              value: each,
              label: FORMATS[each] ?? each,
            }))}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="w-12 shrink-0 text-label text-ink-muted">Size</span>
          <Select
            label="Size"
            value={String(scale)}
            onChange={(value) => setScale(Number(value))}
            items={SCALES.map((each) => ({
              value: String(each),
              label: `${each}x`,
              aside:
                shown.width !== null && shown.height !== null
                  ? dimensions(shown.width * each, shown.height * each)
                  : undefined,
            }))}
          />
        </div>
        {error && <Notice onDismiss={() => setError(null)}>{error}</Notice>}
        {saved && (
          <p className="text-caption break-all text-ink-muted">
            Saved to <span className="mono-value text-ink">{saved}</span>
          </p>
        )}
        <div className="flex items-center gap-2 pt-0.5">
          <span className="min-w-0 flex-1 truncate mono-value text-ink-muted">
            {baseName(stem(image.name))}
            {format}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => void save()}
          >
            {busy && <LoadingMark />}
            Export
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
