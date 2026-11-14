import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { connect } from "@/lib/host";

const root = createRoot(document.getElementById("root")!);

try {
  await connect();
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
} catch (cause) {
  root.render(
    <p className="m-4">
      Could not connect to the host.{" "}
      {cause instanceof Error ? cause.message : String(cause)}
    </p>,
  );
}
