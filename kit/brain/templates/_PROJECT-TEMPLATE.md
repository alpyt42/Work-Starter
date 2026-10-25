# Project: (Name)

> To copy to `projects/internal/<name>/<name>.md`. For a client or a client mission, use `kit/brain/templates/_CLIENT-TEMPLATE.md` and `_MISSION-TEMPLATE.md` instead. This is an INDEX: it summarizes, points to the repo and the notes, and keeps the timeline.
>
> The `../../../` in the links are valid for `projects/<axis>/<name>/`. When in doubt, run `uv run tools/brain/check-links.py` from the workspace root.

- **Status:** active | paused | done
- **Goal:** (one sentence — what "done" looks like)
- **Time tracking:** (reference confirmed by the brain owner, never guessed; optional, remove if unused)
- **Repo:** `../../../repos/(folder)` ← the territory this project indexes (empty if no code)
- **Stakeholders:** [person-name](../../../people/person-name.md)
- **Board:** [tasks](../../../tasks.md)

## Context
(context and constraints — the why, not the how)

## Notes
- [YYYY-MM-DD-topic](notes/YYYY-MM-DD-topic.md) — (what it is about; dated working notes in `notes/`, next to `state/`)
- Handoffs: `handoffs/`

## Registers
> Create `state/actions.md` from [`_ACTIONS-TEMPLATE.md`](../../../../kit/brain/templates/_ACTIONS-TEMPLATE.md), adapting its links to this internal project; `state/decisions.md` (from `_DECISIONS-TEMPLATE.md`) and `state/glossary.md` as needed. These registers are the only place to write actions and decisions; do not copy them into this page.
- [Action register](state/actions.md)
- [Decisions](state/decisions.md) — proposed, accepted, rejected, superseded
- [Glossary](state/glossary.md) — optional: the project's terms, acronyms and transcription errors

## Timeline
> One item per day or per session, one line each — enough to reconstruct *how we got here* without rereading the detail. Only the current month stays here: as soon as it writes in a new month, the agent moves the earlier entries without asking, unchanged, into `journal/YYYY-MM.md` (brain convention) and lists the archived months below (remove that line while nothing is archived).
Previous months: [YYYY-MM](journal/YYYY-MM.md)
- (date) — page created
