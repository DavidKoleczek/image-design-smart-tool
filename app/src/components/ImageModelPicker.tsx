import { Button } from "@/components/ui/button";
import {
  Menu,
  MenuContent,
  MenuGroup,
  MenuGroupLabel,
  MenuItem,
  MenuRadioGroup,
  MenuRadioItem,
  MenuSeparator,
  MenuTrigger,
} from "@/components/ui/menu";
import { Select, type SelectItem } from "@/components/ui/select";
import type { ImageMethods } from "@/lib/api";
import { openKeyDialog, useKey } from "@/lib/key";
import { CHATGPT, CHATGPT_LABEL, imageModelLabel } from "@/lib/request";

// In the model list, opens the dialog about the key rather than picking a model.
const SET_KEY = "set-openai-key";
const OPENAI_GROUP = "OpenAI API";
const CHATGPT_GROUP = "ChatGPT";

/** The image models a request can go to: OpenAI's, greyed out until the API is set up, and ChatGPT's. */
function modelItems(methods: ImageMethods): SelectItem<string>[] {
  const { openai, chatgpt } = methods;
  return [
    ...openai.models.map((model) => ({
      value: model.id,
      label: model.label,
      group: OPENAI_GROUP,
      disabled: openai.ready ? undefined : (openai.problem ?? "Not set up"),
    })),
    {
      value: CHATGPT,
      label: CHATGPT_LABEL,
      group: CHATGPT_GROUP,
      disabled: chatgpt.ready ? undefined : (chatgpt.problem ?? "Not set up"),
    },
  ];
}

/** The image model a request goes to, as a field of a form. */
export function ImageModelSelect({
  value,
  onChange,
  methods,
}: {
  value: string;
  onChange: (model: string) => void;
  methods: ImageMethods;
}) {
  const key = useKey();
  return (
    <Select
      label="Image model"
      value={value}
      onChange={(model) =>
        model === SET_KEY ? openKeyDialog() : onChange(model)
      }
      items={[
        ...modelItems(methods).filter((item) => item.group === OPENAI_GROUP),
        // Where the person looks when the models are greyed out for want of a key.
        ...(key.status?.source === null
          ? [{ value: SET_KEY, label: "Set API key...", group: OPENAI_GROUP }]
          : []),
        ...modelItems(methods).filter((item) => item.group === CHATGPT_GROUP),
      ]}
    />
  );
}

/** The image model the agent makes its images with, as a button beside the message to it. */
export function ImageModelPicker({
  value,
  onChange,
  methods,
}: {
  value: string;
  onChange: (model: string) => void;
  methods: ImageMethods;
}) {
  const key = useKey();
  const items = modelItems(methods);
  return (
    <Menu>
      <MenuTrigger
        render={
          <Button size="sm" aria-label="Image model" className="min-w-0" />
        }
      >
        <span className="truncate">{imageModelLabel(value, methods)}</span>
      </MenuTrigger>
      <MenuContent side="top" align="start" className="w-60">
        <MenuRadioGroup value={value} onValueChange={onChange}>
          {[OPENAI_GROUP, CHATGPT_GROUP].map((group) => (
            <MenuGroup key={group}>
              <MenuGroupLabel>{group}</MenuGroupLabel>
              {items
                .filter((item) => item.group === group)
                .map((item) => (
                  <MenuRadioItem
                    key={item.value}
                    value={item.value}
                    disabled={item.disabled !== undefined}
                    title={item.disabled}
                    closeOnClick
                  >
                    {item.label}
                  </MenuRadioItem>
                ))}
            </MenuGroup>
          ))}
        </MenuRadioGroup>
        {key.status?.source === null && (
          <>
            <MenuSeparator />
            <MenuItem onClick={() => openKeyDialog()}>Set API key...</MenuItem>
          </>
        )}
      </MenuContent>
    </Menu>
  );
}
