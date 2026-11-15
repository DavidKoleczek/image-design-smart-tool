---
name: prompting-chatgpt-images
description: >-
  How to prompt ChatGPT's image generation through `image-design generate-chatgpt-image`: what the prompt says, how
  much to add, and what each image sent is for, with OpenAI's prompting guide for more. Load before writing a call with
  generate-chatgpt-image.
---

The image tool sees only the call: its prompt, passed on as written, and the images it sends. It never sees the
conversation, earlier prompts, or images you did not pass, so the prompt carries everything that matters.

## Write the prompt

1. Name the result: the subject and what it is for, such as an icon seen small, a slide, or a product photo. Then the
   composition and the placement that matters.
1. Say the shape, such as a square icon, a wide banner, or a tall poster. ChatGPT chooses the size and quality, so
   the prompt is the only way to ask for one.
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

`--transparent` asks for a transparent background, for a cutout.

## What each image is for

An image given only for its style, subject, or level of detail means a new image with it as a `--reference`.
Restyling an image while keeping its composition is an edit. Each call makes one image, so variants are one call each.

Images are numbered by their place in the call. An edit sends the image being edited as image 1, then each
`--reference` in the order given. With `--marks`, image 2 is a copy of the image with the marks drawn on it, so the
references start at image 3. A new image starts at the first `--reference`. There is no mask, so point at a region with
marks or name it in words.

Say in the prompt what each image is for and how they combine: "place the cat from image 2 on the sofa in image 1". A
reference lends more than the property named, so a screenshot sent for its shading also lends its shapes. Leave out a
reference whose other qualities are unwanted and put the quality in words, or say what not to take from it. Write
image 2, never "the two images" or "as before".

## OpenAI's prompting guide

For a case this does not cover, or a result that keeps missing, read OpenAI's guide to prompting its image models,
with worked examples such as exact text, logos, diagrams, style transfer, and keeping a character consistent. Its
advice on prompts applies here, but not its API parameters, which this command does not take. The path is relative to
this skill's directory, and the guide is long, so search it for the section you need:
`../prompting-openai-images/references/openai-image-prompting.md`.
