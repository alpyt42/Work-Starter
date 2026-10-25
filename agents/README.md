# agents/ — agents' working area

> The scratch of the AI agents. Session diaries, logs, plans, build scripts, drafts, intermediate notes — everything the agent uses while it works and that is **not meant to be read by a human**. It is neither durable context (→ a brain), nor lasting code (→ `repos/`), nor an output for someone (→ `artifacts/`).

## Structure

One folder per project, then one folder per session when the session deserves to be isolated:

```
agents/
├── <project>/
│   └── YYYY-MM-DD-<session-slug>/
│       ├── diary.md
│       ├── plan.md
│       └── …
└── _cross/          # whatever belongs to no project
```

The project name follows that of the repo or of the memory project concerned, so that the match is obvious.

## Here or in the repo?

- **By default: here.** The most frequent case — the work touches several places.
- **In the repo** if the WIP is really specific to a single repo: then a gitignored folder **inside** that repo (`.agents/`, `scratch/`), clearly separated from the code.
- The plans, build scripts and intermediate renders of a human deliverable stay here during iteration; only the deliverable and its provenance go to `artifacts/`. If the generation code must remain reconstructible after `agents/` is cleaned up, promote it to a suitable repo.

In both cases, never leave scratch lying around at the root of the workspace or in a brain.

## Retention — **promote or lose it**

Apart from this README tracked by Git, the content of this folder is **disposable**: it is ignored by the `Work` repository and is not guaranteed to survive a cleanup. An agent may delete only what it created itself in the same session (its tests, fixtures, intermediate files). Anything older, from another session or from the owner stays, or moves into an `archive/` folder (`agents/archive/`, `agents/<project>/archive/`); the rest of the cleanup is the owner's.

Corollary, the only rule that matters: **if something written here becomes durable, promote it before the end of the session** — a decision or minutes to the project page or a notes folder of the relevant brain, technical documentation to the repo, a deliverable to `artifacts/`. Whatever stays here is considered lost in advance.

Without this rule, this space turns back into exactly the mess it is meant to absorb — just tidied into a folder.
