import { App } from "@modelcontextprotocol/ext-apps";

import { QuietPostMessageTransport } from "@/lib/transport";

export const app = new App(
  { name: "Image Design", version: "1.0.0" },
  { availableDisplayModes: ["inline", "fullscreen"] },
);

export async function connect(): Promise<void> {
  if (window.parent === window) {
    throw new Error(
      "This page is an MCP App view and needs a host. Ask your agent to call `open_app`.",
    );
  }
  await app.connect(
    new QuietPostMessageTransport(window.parent, window.parent),
  );
}
