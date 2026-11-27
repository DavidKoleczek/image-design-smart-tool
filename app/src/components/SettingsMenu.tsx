import type { ReactNode } from "react";

import { ImageModelOrder } from "@/components/ImageModelOrder";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd } from "@/components/ui/kbd";
import { Notice } from "@/components/ui/notice";
import {
  Popover,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip } from "@/components/ui/tooltip";
import { APP_NAME, DOCUMENTATION, VERSION } from "@/lib/brand";
import { app } from "@/lib/host";
import { openKeyDialog } from "@/lib/key";
import { useMethods } from "@/lib/methods";
import { resetLayout, updateSettings, useSettings } from "@/lib/settings";

const ROW =
  "flex h-7 w-full cursor-default items-center gap-2 rounded-sm px-2 text-left whitespace-nowrap hover:bg-hover";

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="px-2 pt-2 pb-2.5">
      <p className="mb-1.5 text-label text-ink-muted">{label}</p>
      {children}
    </div>
  );
}

/** What is about the app itself: its theme, its keys, its layout, and its docs; and the person's defaults for the tool. */
export function SettingsMenu({
  onShortcuts,
}: {
  /** Shows the keyboard shortcuts; absent where there are none, as before a workspace is picked. */
  onShortcuts?: () => void;
}) {
  const { settings, error } = useSettings();
  const { methods } = useMethods();
  const documentation = DOCUMENTATION;

  return (
    <Popover>
      <Tooltip content="Settings">
        <PopoverTrigger
          render={<Button size="sm" icon aria-label="Settings" />}
        >
          <Icon name="sliders" />
        </PopoverTrigger>
      </Tooltip>
      <PopoverContent label="Settings" className="w-75">
        <Section label="Theme">
          <Segmented
            label="Theme"
            size="sm"
            full
            value={settings.theme}
            onChange={(theme) =>
              updateSettings((current) => ({ ...current, theme }))
            }
            options={[
              { value: "system", label: "System", icon: "monitor" },
              { value: "light", label: "Light", icon: "sun" },
              { value: "dark", label: "Dark", icon: "moon" },
            ]}
          />
        </Section>
        {error && <Notice className="mx-1 mb-1">{error}</Notice>}
        {methods && (
          <>
            <hr className="-mx-1 my-1 border-line" />
            <Section label="Agent's Default Image Method">
              <p className="mb-1.5 text-caption text-ink-muted">
                The priority order the design-image agent picks an image
                generation method
              </p>
              <ImageModelOrder methods={methods} />
            </Section>
          </>
        )}
        <hr className="-mx-1 my-1 border-line" />
        {onShortcuts && (
          <PopoverClose className={ROW} onClick={onShortcuts}>
            <span className="flex-1">Keyboard shortcuts</span>
            <Kbd>?</Kbd>
          </PopoverClose>
        )}
        <PopoverClose className={ROW} onClick={openKeyDialog}>
          OpenAI API key
        </PopoverClose>
        {onShortcuts && (
          <button type="button" className={ROW} onClick={resetLayout}>
            Reset layout
          </button>
        )}
        {documentation && (
          <button
            type="button"
            className={ROW}
            onClick={() => void app.openLink({ url: documentation })}
          >
            <span className="flex-1">Documentation</span>
            <Icon name="link-out" className="text-ink-muted" />
          </button>
        )}
        <hr className="-mx-1 my-1 border-line" />
        <p className="flex h-6 items-center px-2 mono-annotation text-ink-muted">
          {APP_NAME}
          {VERSION && ` ${VERSION}`}
        </p>
      </PopoverContent>
    </Popover>
  );
}
