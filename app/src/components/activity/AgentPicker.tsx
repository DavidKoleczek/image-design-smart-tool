import { Button } from "@/components/ui/button";
import { FormRow } from "@/components/ui/form-row";
import {
  Menu,
  MenuContent,
  MenuGroup,
  MenuGroupLabel,
  MenuRadioGroup,
  MenuRadioItem,
  MenuSeparator,
  MenuTrigger,
} from "@/components/ui/menu";
import { Select } from "@/components/ui/select";
import type { AppDesignRequest, ImageMethods } from "@/lib/api";
import { effortLabel, providerLabel, type Agent } from "@/lib/drawing";
import { updateAppState } from "@/lib/state";

/** Whose agent is picked: the one that draws SVGs, or the one that directs the image models. */
export type Picks = "svg" | "design";

function updateAgent(picks: Picks, change: Partial<AppDesignRequest>) {
  updateAppState((current) => ({
    ...current,
    [picks]: { ...current[picks], ...change },
  }));
}

/** The agent a message goes to, by its agent provider, and how hard it thinks. */
export function AgentPicker({
  agent,
  picks,
  methods,
}: {
  agent: Agent;
  picks: Picks;
  methods: ImageMethods;
}) {
  const { models } = methods[picks];
  const providers = [...new Set(models.map((model) => model.agent_provider))];
  return (
    <Menu>
      <MenuTrigger
        render={
          <Button
            size="sm"
            disabled={models.length === 0}
            aria-label="Agent and reasoning effort"
            className="min-w-0"
          />
        }
      >
        <span className="truncate">{agent.entry?.label ?? agent.model}</span>
        <span className="text-ink-muted">{effortLabel(agent.effort)}</span>
      </MenuTrigger>
      <MenuContent side="top" align="start" className="w-60">
        <MenuRadioGroup
          value={`${agent.provider}/${agent.model}`}
          onValueChange={(value: string) => {
            const [provider, ...model] = value.split("/");
            updateAgent(picks, {
              agent_provider: provider,
              model: model.join("/"),
            });
          }}
        >
          {providers.map((provider) => (
            <MenuGroup key={provider}>
              <MenuGroupLabel>{providerLabel(provider)}</MenuGroupLabel>
              {models
                .filter((model) => model.agent_provider === provider)
                .map((model) => (
                  <MenuRadioItem
                    key={model.id}
                    value={`${provider}/${model.id}`}
                    closeOnClick
                  >
                    {model.label}
                  </MenuRadioItem>
                ))}
            </MenuGroup>
          ))}
        </MenuRadioGroup>
        {agent.entry && (
          <>
            <MenuSeparator />
            <MenuGroup>
              <MenuGroupLabel>Reasoning effort</MenuGroupLabel>
              <MenuRadioGroup
                value={agent.effort}
                onValueChange={(value: string) =>
                  updateAgent(picks, { reasoning_effort: value })
                }
              >
                {agent.entry.reasoning_efforts.map((effort) => (
                  <MenuRadioItem key={effort} value={effort} closeOnClick>
                    {effortLabel(effort)}
                  </MenuRadioItem>
                ))}
              </MenuRadioGroup>
            </MenuGroup>
          </>
        )}
      </MenuContent>
    </Menu>
  );
}

/** The agent and how hard it thinks, as rows of the form a new image is asked for with. */
export function AgentRows({
  agent,
  picks,
  methods,
}: {
  agent: Agent;
  picks: Picks;
  methods: ImageMethods;
}) {
  const { models } = methods[picks];
  return (
    <>
      <FormRow label="Agent">
        <Select
          label="Agent"
          value={`${agent.provider}/${agent.model}`}
          disabled={models.length === 0}
          onChange={(value) => {
            const [provider, ...model] = value.split("/");
            updateAgent(picks, {
              agent_provider: provider,
              model: model.join("/"),
            });
          }}
          items={models.map((model) => ({
            value: `${model.agent_provider}/${model.id}`,
            label: model.label,
            group: providerLabel(model.agent_provider),
          }))}
        />
      </FormRow>
      <FormRow label="Reasoning">
        <Select
          label="Reasoning effort"
          value={agent.effort}
          disabled={!agent.entry}
          onChange={(reasoning_effort) =>
            updateAgent(picks, { reasoning_effort })
          }
          items={(agent.entry?.reasoning_efforts ?? [agent.effort]).map(
            (effort) => ({ value: effort, label: effortLabel(effort) }),
          )}
        />
      </FormRow>
    </>
  );
}
