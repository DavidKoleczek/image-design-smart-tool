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
