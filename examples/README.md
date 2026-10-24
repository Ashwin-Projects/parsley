# Examples

Demo-ready English input files, one sentence per line (the CLI file-mode format, Phase 5).

- `valid/` - sessions that compile cleanly
- `invalid/` - unsupported input (rejected, with a suggestion)
- `ambiguous/` - input that triggers a clarification

The canonical, machine-checked fixtures live in [`tests/fixtures/`](../tests/fixtures/).
The files here are runnable sessions built from those fixtures. They will be added once
file mode exists (Phase 5), so that each can be run end to end.
