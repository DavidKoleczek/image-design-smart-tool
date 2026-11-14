const POLL_MS = 1000;

/**
 * Calls `tick` now, then again each `ms` after it settles, so a slow answer never has another asked for behind it.
 * Returns what stops it.
 */
export function poll(tick: () => Promise<void>, ms = POLL_MS): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const run = async () => {
    await tick();
    if (!stopped) {
      timer = setTimeout(run, ms);
    }
  };
  void run();
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}
