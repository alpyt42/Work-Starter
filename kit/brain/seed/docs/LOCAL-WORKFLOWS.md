# Local workflow settings

The reusable procedures (public scripts and skills) live in the workspace; only the private skills specific to this brain live in [`skills/`](../skills/README.md). This document keeps only the settings specific to this brain and the exceptions confirmed by the owner. The states tracked by Git are in `.data/` ([`README`](../.data/README.md)); API tokens stay in an ignored `.env` at the workspace level, read only by the scripts.

## Checkout location

- Workspace root: (to be completed, for example `~/Work/`), with the brain in `brain/` (or `brain-<name>`). The workspace scripts find the default brain next to `tools/` (`"defaultBrain"` in the ignored `work-config.local.json`, else `brain/`, else the only brain); `BRAIN_DIR` forces another location.

## Meetings

- Transcripts to read: the `transcripts_dir` folder of [`.data/local-paths.json`](../.data/local-paths.json) (path relative to `$HOME`, outside the workspace, never cited in a Markdown file). Audio recordings: `recordings_dir`; do not open, move or delete them without an explicit request.
- The transcript and the audio stay where they are; only the Markdown minutes (CR) enter the brain, with a provenance described in words (tool, recorder, date). Tracking of the processed files: `.data/transcripts.json`.
- Format of a transcript line: (to be completed according to the recording tool).

## Messages

- Cursors and processed ids: `.data/messages-state.json`.
- Triage exceptions: (none for now).
