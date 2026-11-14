import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import type { OpenAIKeyStatus } from "@/lib/api";
import { describe } from "@/lib/errors";
import { clearKey, closeKeyDialog, enterKey, useKey } from "@/lib/key";

function where(status: OpenAIKeyStatus): string {
  if (status.source === "environment") {
    return status.saved
      ? "The key in use comes from OPENAI_API_KEY in the environment the app was started in. A saved key is kept too, for when the environment has none."
      : "The key in use comes from OPENAI_API_KEY in the environment the app was started in.";
  }
  return status.source === "saved"
    ? "A key is saved in this computer's credential store."
    : "No key is set. The OpenAI API models need one.";
}

/**
 * The OpenAI API key: where it comes from, and a way to save one or forget it. The key is typed into a window of the
 * machine the server runs on and kept in its credential store, so the view never holds it.
 */
export function KeyDialog() {
  const { open, status } = useKey();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enter = async () => {
    setAsking(true);
    setError(null);
    try {
      await enterKey();
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setAsking(false);
    }
  };

  const remove = async () => {
    setError(null);
    try {
      await clearKey();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && closeKeyDialog()}>
      <DialogContent title="OpenAI API key" className="sm:max-w-110">
        <div className="flex flex-col gap-3 px-5 py-4">
          {status ? <p>{where(status)}</p> : <LoadingMark />}
          <p className="text-caption text-ink-muted">
            A key is typed into a window on this computer, not here, and kept in
            its credential store.
          </p>
          {asking && (
            <Notice tone="neutral" icon="monitor">
              Enter the key in the window that opened on this computer. It may
              be behind this one.
            </Notice>
          )}
          {error && <Notice onDismiss={() => setError(null)}>{error}</Notice>}
        </div>
        <DialogFooter className="justify-end">
          {status?.saved && (
            <Button
              variant="secondary"
              disabled={asking}
              onClick={() => void remove()}
            >
              Remove saved key
            </Button>
          )}
          <Button
            variant="primary"
            disabled={asking}
            onClick={() => void enter()}
          >
            {asking && <LoadingMark />}
            {status?.saved ? "Replace key" : "Enter key"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
