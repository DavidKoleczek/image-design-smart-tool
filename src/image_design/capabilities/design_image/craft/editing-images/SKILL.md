---
name: editing-images
description: >-
  Edit an image that exists with the image-design CLI without losing what it has: what changes and what stays, how
  versions and drafts work, how to make several changes, starting from the right version, marks, and when to merge
  edits with a script. Load before any call that edits an image.
---

An edit sends the image as image 1 with your prompt, and nothing else from before: not the first prompt, not the style
reference, not what the person said last turn. Whatever the call does not hold in place is open to change.

## How versions and drafts work

Each call on an image saves the result as a new version and replaces the image's file with it, even when the call
starts from an older version with `--version`. The user sees the new version right away.

To try a change without changing the image, add `--draft` to the call. The result is saved apart as a draft, and the
call prints where. The image and its versions stay as they are, and the user still sees the draft in your conversation.
Several drafts can run at the same time, including from the same version, so you can try different changes or
different ways of making one. A draft's run id is the name of the folder its file is in.

To save a draft you like, or a file you made yourself such as a merged image, as the next version, run:

```bash
image-design add-image-version --name rooms/living-room.png --draft <run id>
image-design add-image-version --name rooms/living-room.png --path merged.png
```

Always make calls on the image itself or on another image in the same images directory. Never copy the image into your
work directory and make calls on the copy: the user can't see those calls in your conversation. Use drafts instead.

Only one call that makes a version can run on an image at a time, so wait for it to finish before starting the next.
Drafts don't have to wait.

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

## Making several changes

First make any vague request specific. For "add more life", decide which part changes and how, picking what works best
for the image.

By default, make one change per call, each building on the result of the last. Do removals first, and do a change of
style in a call of its own. Each call redraws the whole image, so small details elsewhere can drift. That is fine for
most images, and it works best when a change affects its surroundings, such as lighting or shadows.

Other options:

- Small changes that don't touch each other can go in one call. Mark each one, then check that every change happened,
  and redo any that didn't in a call of its own.
- When everything outside the changes must stay exactly the same, make each change as a draft from the same version,
  all at once, then merge them with a script, as described below.
- When you are unsure how a change will come out, try a few ways as drafts and keep the best one.

Look at each result before moving on.

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

## Merge with a script when pixels must not move

Image models redraw the whole image, so none of them can promise that the rest stays exactly the same. When it must,
such as in a screenshot or an asset already in use, make the edit as a draft, then use a script to paste only the
changed area from the draft onto the version it started from, with a soft edge.
`image-design view-image --name <image> --json` gives each version's file. Resize the draft to match that version
first, since an edit can come back at a different size. Then save the merged image as the next version, naming each
draft it was made from:

```bash
image-design add-image-version --name rooms/living-room.png --path merged.png --draft <run id> --draft <run id>
```

A merge can leave a visible seam or a change in color at the edge, so look at it closely. If small changes elsewhere
are acceptable, skip the merge and keep the draft as it is. It is simpler and blends in better.

A script is also the way to an exact crop, a resize, or removing a flat background.
