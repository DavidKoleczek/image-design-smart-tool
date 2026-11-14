import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";

const SHORTCUTS: [string[], string][] = [
  [["1", "2"], "Markup or Mask"],
  [["V", "H"], "Select or pan"],
  [["O", "R", "A", "P"], "Circle, box, arrow, or sketch"],
  [["B", "E"], "Paint or erase the mask"],
  [["Del"], "Delete the mark picked, or the images and folders selected"],
  [["F2"], "Rename the image or folder selected"],
  [["Ctrl", "A"], "Select every image and folder"],
  [["Ctrl", "X"], "Cut the images and folders selected"],
  [["Ctrl", "C"], "Copy them"],
  [["Ctrl", "V"], "Paste into the folder selected"],
  [["+", "-"], "Zoom in or out"],
  [["F"], "Fit"],
  [["C"], "Compare with the version before"],
  [["Space"], "Play or pause an animation"],
  [[",", "."], "Previous or next frame"],
  [["/"], "Search images"],
  [["["], "Your images"],
  [["]"], "Request"],
  [["N"], "New image"],
  [["Ctrl", "Enter"], "Generate"],
  [["?"], "This list"],
  [["Esc"], "Close"],
];

/** Every key the app answers to. */
export function ShortcutsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Keyboard shortcuts" className="sm:max-w-90">
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 px-5 pt-4 pb-5">
          {SHORTCUTS.map(([keys, action]) => (
            <div key={action} className="contents">
              <dt className="flex gap-1">
                {keys.map((key) => (
                  <Kbd key={key}>{key}</Kbd>
                ))}
              </dt>
              <dd>{action}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
