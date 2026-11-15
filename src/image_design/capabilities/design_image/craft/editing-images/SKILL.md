---
name: editing-images
description: >-
  Edit an image that exists with the image-design CLI without losing what it has: what changes and what stays, one
  narrow change at a time, from the right version, with marks or a composite made with a script. Load before any call
  that edits an image.
---

An edit sends the image as image 1 with your prompt, and nothing else from before: not the first prompt, not the style
reference, not what the person said last turn. Whatever the call does not hold in place is open to change.

## Say what changes, then what stays

Name the change exactly. Then list what stays: shapes, arrangement, shading, colors, camera angle, background, and
anything the person approved. Close open scope: "simpler" can mean fewer objects or a plainer rendering, so decide
which from the request and say it.

```text
Input images: Image 1: room photo
Primary request: replace only the white chairs with wooden chairs
Constraints: preserve camera angle, room lighting, floor shadows, and surrounding objects; keep all other aspects unchanged
```

- Repeat what stays on every iteration, also when this turn said nothing about it. Drift adds up one edit at a time.
- Send an earlier style or subject reference again when its influence has to hold, with its purpose stated again.
  It is under the earlier run's `run_folder` in `image-design read-image-activity --name <image> --json`.

## One narrow change at a time

Split a request with several changes ("remove the sign, make it dusk, add more life") into separate calls, removals
first and a change of style on its own. Turn a vague one such as "add more life" into a concrete change (which part,
what kind) before it is sent, choosing the reading that serves the image best.

## Edit from the right version

An edit starts from the image's file. `--version v2` starts from an earlier version instead, and
`image-design view-image --name <image>` lists them. When an edit went wrong, go again from the version before it
rather than correcting the correction.

To start an image over without its current look leaking in, create it under a scratch name, keep the result as the
image's next version with `image-design add-image-version --name <image> --path <file>`, then delete the scratch image
with `image-design delete-image --name <scratch>`.

## Marks

Marks (`--marks marks.json`) point at things: which chair, which window. They say what the request is about, not where
pixels may change, so still list what stays. Give each mark a `note` and refer to it as mark 1, mark 2 in the prompt;
the tool adds a line for each after the prompt. Marks you are given as a file can be passed on as they are; put them in
words instead when the thing is easy to name.

```json
[{"shape": "circle", "points": [[0.40, 0.50], [0.60, 0.90]], "color": "red", "note": "this chair"}]
```

Points are fractions of the width and height from the top left: two opposite corners for a `circle` or `box`, the tail
then the head for an `arrow`, and each point along a `sketch`.

## Composite when pixels must not move

When everything outside the change has to stay pixel for pixel, such as an asset already in use or a
screenshot, no image model promises it. Make the edit, then with a script paste only the changed region from the
result into the original, with a soft edge. Scale the result to the original's size first, since an edit can come
back at another size. Keep the composite as the image's next version:

```bash
image-design add-image-version --name rooms/living-room.png --path composite.png
```

A script is also the way to an exact crop, a resize, or removing a flat background.
