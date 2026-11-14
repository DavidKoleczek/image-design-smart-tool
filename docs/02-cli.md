# CLI Reference

The CLI is a thin wrapper over the [library](01-library.md): one command per capability, taking the same arguments under the same names.
What each argument means and what a capability returns or raises is documented there. This page covers only what the CLI adds.

`image-design --version` (or `-V`) prints the distribution name and its installed version.

Commands print readable text by default. Where a command also offers structured output, it takes `--json`.

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

- `references`: Repeat `--reference <path>` for each file.
- `marks`: Pass `--marks <path>`, a JSON file that holds a list of marks.
- `size` and `canvas`: The width and height joined by `x`, such as `--size 1024x1024`.
- `max_shapes`, `max_colors`, `max_bytes`: A number, or `none` for no limit.
- `resume_session`: `true`, `false`, or a session ID.

`intelligence` is not available from the CLI.

## Generate and draw images

`generate-openai-image`, `generate-chatgpt-image`, and `draw-svg-image` wait for the run to end, then print the path of each image they made:

```console
$ image-design draw-svg-image "A flat vector sailboat on calm water at sunset. No text." --name sailboat.svg
.image-design/sailboat.svg
```

Progress is printed to stderr while the run works. With `--json`, each event of the run is printed to stdout as one line of JSON instead, and the last event has the result.

The command exits with 0 if the run finished, and with 1 if it failed, timed out, or was cancelled. Ctrl+C cancels the run.

With `--detach`, the command exits as soon as the run starts, and the run continues in the background. Use the other commands to follow it:

```bash
image-design draw-svg-image "A flat vector sailboat on calm water at sunset. No text." --name sailboat.svg --detach
image-design read-image-activity --name sailboat.svg
image-design steer-svg-image --name sailboat.svg --message "Make the sail red."
image-design cancel-image --name sailboat.svg
```

## Other commands

```
image-design list-images                                         the images in the directory
image-design view-image --name <name>                            one image and its versions
image-design restore-image-version --name <name> --version <v>   put an earlier version back
image-design move-image --name <name> --new-name <name>          rename or move an image
image-design delete-image --name <name>                          delete an image and its data
image-design cancel-image --name <name>                          stop the run on an image
image-design read-image-activity --name <name>                   the history of an image
image-design steer-svg-image --name <name> --message <text>      send a message to the agent
image-design check-svg-image --name <name>                       measure a drawing
image-design export-svg-image --name <name> --output <path>      render a drawing to a file
image-design list-image-methods                                  the ways to make an image
image-design list-intelligence-models                            the models an agent can use
image-design manifest                                            the tool's manifest
image-design app [--port <n>]                                    serve the app in a browser page
image-design mcp                                                 serve the app over stdio as an MCP App
```

Every command that works on images also takes `--directory` and `--data-directory`.

`steer-svg-image`, `cancel-image`, and `delete-image` print nothing. `manifest` prints JSON. The others print text, or JSON with `--json`.

`app` calls `lib.app_server().open()`, prints its URL, and keeps serving until Ctrl+C, which exits 0.
`mcp` calls `image_design.adapters.mcp.run_stdio()`, for MCP clients that launch the server themselves. stdin and stdout carry only MCP messages until the client disconnects.

A command exits with 1 and prints the error to stderr when the library raises `ImageDesignError`. An invalid command line exits with 2.
