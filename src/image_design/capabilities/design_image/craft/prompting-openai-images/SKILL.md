---
name: prompting-openai-images
description: >-
  How to prompt OpenAI's image models through `image-design generate-openai-image`: what the prompt says, how much to
  add, what each image sent is for, and the flags that change the result, with OpenAI's full guides for more. Load
  before writing a call with generate-openai-image.
---

The image model sees only the call: its prompt, the images it sends, and its flags. It never sees the conversation,
earlier prompts, or images you did not pass, so the prompt carries everything that matters.

## Write the prompt

1. Name the result: the subject and what it is for, such as an icon seen small, a slide, or a product photo. Then the
   composition and the placement that matters.
1. Describe what is visible: materials, lighting, colors, and the medium. Ask for "photorealistic" when that is the
   goal. Give scale, atmosphere, and color rather than mood words alone.
1. For people, say the framing, the scale, where they look, and what they do with their hands: "full body visible,
   feet included", "hands gripping the handlebars".
1. Put text the image must show in quotes, exactly, with where it goes and its typography. Spell unusual words letter
   by letter, and ask for no other text.
1. Name the level of detail and what to leave out, since "simple" alone is open.

A detailed request goes in a clear order, with nothing new added. A vague one gets framing, composition, the intended
use, and the level of polish, but never objects, characters, text, brand names, or palettes that were not asked for or
implied.

For a lot to say, labeled lines in the order scene, subject, details, constraints read best. Use only the lines that
are needed:

```text
Input images: Image 1: previous character anchor illustration
Primary request: continue the story with the same character in a new scene and action
Scene/backdrop: snowy forest after a winter storm
Subject: same young forest hero gently helping a frightened squirrel out of a fallen tree
Style/medium: same children's book watercolor illustration style as Image 1
Constraints: do not redesign the character; preserve facial features, proportions, outfit, color palette, and personality; no text; no watermark
```

## What each image is for

An image given only for its style, subject, or level of detail means a new image with it as a `--reference`.
Restyling an image while keeping its composition is an edit. Each call makes one image, so variants are one call each.

Images are numbered by their place in the call. An edit sends the image being edited as image 1, then each
`--reference` in the order given. A new image starts at the first `--reference`. Marks and a mask go as layers of their
own, with no number.

Say in the prompt what each image is for and how they combine: "place the cat from image 2 on the sofa in image 1". A
reference lends more than the property named, so a screenshot sent for its shading also lends its shapes. Leave out a
reference whose other qualities are unwanted and put the quality in words, or say what not to take from it. Write
image 2, never "the two images" or "as before".

## Flags that change the result

- `--quality`: how much fine detail the model can render, such as texture and small lettering. `low` suits a draft;
  small text and dense layouts need `medium` or more.
- `--complexity`: how much the model plans before it renders. The default, `high`, suits a prompt that leaves the
  design open. `low` suits a change to one detail, so the rest is not planned again.
- `--size`: multiples of 16, with a width to height ratio from 1:3 to 3:1, such as `1024x1024`, `1536x1024`, or
  `1024x1536`. An edit keeps the image's size, rounded to the nearest one the model accepts, unless one is given.
- `--background transparent`: a cutout with real transparency, in a `.png` or `.webp`.
- `--mask mask.png`: bounds where an edit's change goes, for a change confined to one region such as the sky or a
  corner. It is a PNG the size of the version being edited, transparent where changes may go and opaque elsewhere,
  made with a script from the image's own size. Only for still images, and never with marks. The model treats it as
  guidance, so pixels outside it can still shift.

To compare settings, change one at a time.

## OpenAI's full guides

For a case this does not cover, or a result that keeps missing, read OpenAI's own pages. Paths are relative to this
skill's directory. They are long, so search them for the section you need:

- `references/openai-image-prompting.md`: how to prompt the image models, with worked examples such as exact text,
  logos, diagrams, markup, style transfer, and keeping a character consistent.
- `references/openai-image-generation.md`: the guide to creating and editing images with the Images API.
- `references/openai-images-generate.md` and `references/openai-images-edit.md`: the API's reference for creating and
  editing, which the command's flags map onto.
