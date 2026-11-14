import type { ImageRunStatus } from "@/lib/api";

const LABELS: Record<ImageRunStatus, string> = {
  running: "Working",
  done: "Done",
  failed: "Failed",
  cancelled: "Stopped",
  "timed-out": "Timed out",
};

export function statusLabel(status: ImageRunStatus): string {
  return LABELS[status];
}

export function failed(status: ImageRunStatus): boolean {
  return status === "failed" || status === "timed-out";
}
