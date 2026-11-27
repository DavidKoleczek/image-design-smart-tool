# CLI Reference

The CLI is a thin wrapper over the [library](01-library.md): one command per capability, taking the same arguments under the same names.
What each argument means and what a capability returns or raises is documented there. This page covers only what the CLI adds.

`image-design --version` (or `-V`) prints the distribution name and its installed version.

## Help

```
image-design -h                 summary of the tool's capabilities
image-design --help             the tool's help as a skill
image-design <command> -h       summary of one command
image-design <command> --help   that command's skill
```

`--help` on the tool prints what `lib.skill()` returns and on a command what `lib.skill("<command>")` returns; the CLI adds nothing of its own.

## Arguments

A command has the name of its function, with dashes in place of underscores. `prompt` is positional, and every other argument is an option of the same name:

```bash
image-design generate-openai-image "A paper-cut cactus in a terracotta pot." --name concepts/cactus.png --quality high
```

A few arguments are written differently on the command line:

- `paths` for `import-images`: Positional, one or more files and folders.
- `references`: Repeat `--reference <path>` for each file.
- `drafts` for `add-image-version`: Repeat `--draft <run id>` for each draft.
- `marks`: Pass `--marks <path>`, a JSON file that holds a list of marks.
- `size` and `canvas`: The width and height joined by `x`, such as `--size 1024x1024`.
- `max_bytes`, and `timeout_seconds` for `draw-svg-image` and `design-image`: A number, or `none` for no limit.
- `resume_session`: `true`, `false`, or a session ID.

`intelligence` is not available from the CLI.

## Generate and draw images

`generate-openai-image`, `generate-chatgpt-image`, and `draw-svg-image` wait for the run to end, then print the path of each image they made:

```console
$ image-design draw-svg-image "A flat vector sailboat on calm water at sunset. No text." --name sailboat.svg
.image-design/sailboat.svg
```

With `--draft`, the path printed is the draft's file, in a folder named by the draft's run id. Progress is printed to stderr while the run works. With `--json`, each event of the run is printed to stdout as one line of JSON instead, and the last event has the result.

The command exits with 0 if the run finished, and with 1 if it failed, timed out, or was cancelled. Ctrl+C cancels the run.

With `--detach`, the command exits as soon as the run starts, and the run continues in the background. Use the other commands to follow it:

```bash
image-design draw-svg-image "A flat vector sailboat on calm water at sunset. No text." --name sailboat.svg --detach
image-design read-image-activity --name sailboat.svg
image-design steer-svg-image --name sailboat.svg --message "Make the sail red."
image-design cancel-image --name sailboat.svg
```

## Design images with an agent

`design-image` waits for the agent to end, then prints what it said last and the path of the image:

```console
$ image-design design-image "Less detail: no flower buds or spines." --name concepts/cactus.png
v2 has no buds or spines, and the shading and background match v1.
.image-design/concepts/cactus.png
```

What the agent says and the tools it calls are printed to stderr. `--json`, `--detach`, the exit codes, and Ctrl+C work as for the generate commands. `steer-image` sends the agent a message, and `cancel-image` stops it and the calls it has going.

The agent runs this installation's `image-design` on its PATH, so each call it makes is a command like those above. `--image-model` picks what it makes its images with: an OpenAI image model, or `chatgpt`. Without it, the first of `config`'s `design_image_models` that is set up and makes the image is picked. Its calls to any other are refused, and it chooses every other setting of a call itself. Each call is a run of its own that names the agent's run as its `parent`.

## Other commands

```
image-design list-images                                         the images in the workspace
image-design view-image --name <name> [--frames-output <dir>]   one image, its versions, and its frames
image-design restore-image-version --name <name> --version <v>   put an earlier version back
image-design move-image --name <name> --new-name <name>          rename or move an image
image-design copy-image --name <name> --new-name <name>          copy an image and its data
image-design import-image --path <file> [--name <name>]          bring an image file in
image-design import-images <path>... [--folder <folder>]         bring files and folders of images in
image-design add-image-version --name <name> --path <file>       keep a file as an image's next version
image-design delete-image --name <name>                          delete an image and its data
image-design create-folder --name <folder>                       make a folder
image-design move-folder --name <folder> --new-name <folder>     rename or move a folder
image-design delete-folder --name <folder>                       delete a folder and its images
image-design relink-images                                       find images moved outside the tool
image-design cancel-image --name <name>                          stop the run on an image
image-design read-image-activity --name <name>                   the history of an image
image-design steer-image --name <name> --message <text>          send a message to the image's agent
image-design steer-svg-image --name <name> --message <text>      send a message to the drawing's agent
image-design check-svg-image --name <name>                       measure a drawing
image-design export-svg-image --name <name> --output <path>      render a drawing to a file
image-design list-image-methods                                  the ways to make an image
image-design list-intelligence-models                            the models an agent can use
image-design config [--design-image-models <m,m>]                your defaults, such as the agent's image models
image-design manifest                                            the tool's manifest
image-design app [--port <n>]                                    serve the app in a browser page
image-design mcp                                                 serve the app over stdio as an MCP App
```

Every command that works on images also takes `--workspace`, the project's top-level directory, which defaults to the working directory. A `--name` is a path in the workspace's `.image-design`.

`steer-image`, `steer-svg-image`, `cancel-image`, and `delete-image` print nothing. `delete-folder` prints only the files it left. `create-folder` and `move-folder` print the folder's name. `import-images` prints the path of each image it brought in, and what it left out on stderr, and exits 1 when nothing came in. `manifest` prints JSON. The others print text, or JSON with `--json`.

`move-image`, `copy-image`, `import-image`, `create-folder`, and `move-folder` take `--numbered`. For `relink-images`, repeat `--likely <name>` for each image.

`app` calls `lib.app_server().open()`, prints its URL, and keeps serving until Ctrl+C, which exits 0. It can be started from any directory. It opens on the workspace opened last, or asks the user to pick one first, and the user can switch workspaces in it. `--name` opens it on an image, and exits 1 when there is no workspace to open it in.
`mcp` calls `image_design.adapters.mcp.run_stdio()`, for MCP clients that launch the server themselves. It shows the working directory, which is the session's project. stdin and stdout carry only MCP messages until the client disconnects.
For both, `--workspace` sets the workspace the app opens on.

A command exits with 1 and prints the error to stderr when the library raises `ImageDesignError`. An invalid command line exits with 2.
