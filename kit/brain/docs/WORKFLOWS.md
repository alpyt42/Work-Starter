# Workflows — how to use this memory in practice

The system is just Markdown files. The value comes from a few simple habits. Read this once; it answers "what do I edit, when, and when do I ask the agent?"

## The central files

| File | What it is | Who writes in it | Frequency |
|---|---|---|---|
| `inbox/inbox.md` | Raw capture scratchpad | You throw things in; the agent empties it | You: all day long |
| `inbox/` | Whole notes to process (one file per note) | You drop them; the agent dispatches and deletes | As needed |
| `state/actions.md` | A project's action register, the only place where an action is written | The agent (and you) | As work progresses |
| `tasks.md` | Daily focus, per-project list and kanban over all the registers | Nobody: it is computed | You create, schedule and change the state of actions |

In one line: **inbox = thoughts land here · registers = actions, once · tasks = the view to steer by.** Decisions are authoritative in `state/decisions.md` (see [`AGENTS.md`](../AGENTS.md#source-of-truth), "Source of truth").

## Use the list and the kanban in Obsidian

1. **Create**: open Tasks (`tasks.md`), then click **New action**. Choose the project (prefixed with the brain name when the workspace holds several: the form lists the registers of every brain), the title, the owner, the state, the priority and the optional due date. The form adds the action to the right register with its ID; Cancel stops the creation.
2. **Plan your day**: look at "Today" and "In progress". In "Up next" or in a project, use the 📝 pencil to set **Scheduled** to today on the actions you want to work on. `⏳` says when you work; `📅` says when you must deliver. You can pick up to three actions to keep a day readable.
3. **Move forward**: from the list or the kanban (`tasks.md`), right-click the checkbox or use the 📝 pencil → state `[/]` to start, `[w]` after a reminder when you are waiting for an answer. The columns are recomputed; they do not move by drag and drop.
4. **Finish**: tick the checkbox. Tasks writes `[x]` and the completion date in the register; the next maintenance pass files the line under `Done`. To cancel, choose `[-]` and keep the reason in the register.
5. **Review**: "Follow up" gathers every wait; the projects show the open actions of all owners. Textual due dates ("before…", "to be confirmed…") are read in the register.

The [conventions](CONVENTIONS.md#tasks-board-and-inbox) detail the filters and the required plugins; the guide `kit/obsidian/README.md` explains how to set up Obsidian on another machine.

In a local browser, `uv run tools/tasks-web/tasks-web.py` opens a sidebar with the Today, Actions, Board, Timeline, Notes, Search, Tools and Sync views, with the **New action** and **New note** buttons ([guide](../../../tools/tasks-web/README.md)). The interface edits the same registers; refresh the page after an edit made elsewhere. Its Sync view is the one place where a person saves and sends a brain without a terminal: one card per brain, a confirmation, then `git add -A`, `git commit` (`docs: save N notes from tasks-web`) and `git push` of that brain only, with the brain's hooks; the agents keep following [`GIT.md`](GIT.md) (an explicit request for each action, staged paths only).

## The two ways to interact (use both)

### Workflow A — Edit the files, then ask the agent (the daily backbone)
1. All day long, throw anything into `inbox/inbox.md` — fast, rough, unsorted. A whole note (a meeting taken by hand, pasted text) goes into its own file of `inbox/` instead.
2. Once a day, open the agent at the root and say **"triage my inbox"** (or `/inbox`) with the workspace's `inbox` skill: it first shows an "item → destination" table to validate, then applies it.
3. It reads each line of `inbox/inbox.md`, then each other note of `inbox/`, and files every item according to the [what-goes-where table](../AGENTS.md#where-information-goes): action → the project's register (outside a mission: `projects/internal/setup/`) · person → `people/` · mission fact → timeline line (current month), `state/` register or dated note in `notes/`; `workstreams/` only to update a reference doc · durable fact about you → `me/about-me.md` (proposed) · idea without a mission → `projects/internal/setup/notes/` · urgent → explicit priority or due date kept, state `[/]` only if the work has started · trash → deleted. A note from `inbox/` can produce several items; meeting minutes or an account from a third party become a dated source. Then it empties the inbox, deletes the processed notes of `inbox/` (except its `README.md`) and shows you what moved where.

### Workflow B — Ask directly, the agent edits the files (for immediate intent)
- "Add a task: follow up with X on the quote" → adds the action to the project's register
- "Note that Y approved the mock-up" → updates the mission and the person page if that position is useful there, with the source
- "Take a note: …" with no project given → creates the note in `inbox/`, to dispatch at the next triage (collection convention)
- "Set task Z in progress" → puts `[/]` on its line in the register
- "What is my schedule?" → runs `uv run tools/brain/action.py board` (complete table by project; the daily focus is in `tasks.md`), summarizes
- "Start a new mission at X" → creates `projects/clients/<client>/missions/<mission>/<mission>.md` and links it to the client index

**Rule of thumb:** in full flow and not wanting to think about structure → the inbox (A). You know exactly what you want to change → say it (B). Both keep Markdown as the source of truth.

### "Process my brain / my inbox / my actions" — reconciliation
A third reflex, on top of A and B: you tinkered with files by hand during the day (ticked boxes, dropped lines, moved things around), and you ask the agent to **square away your manual work**: clean up the form, file the ticked actions under `Done` in their register, dispatch what is lying around. It **does not archive** a mission or a folder on its own — moving things into `archive/` remains a gesture you ask for.

## Rhythm — on demand
No fixed ritual: passes run when you ask for them. The agent does not trigger them by itself, but can **suggest** a pass when it sees things piling up (overflowing inbox, overdue actions, ticked actions still under `Open`). The only exception: the two monthly moves (timeline → `journal/`, actions closed for more than 30 days → archive), which the agent does without asking as soon as it writes in a project in a new month or the doctor reports them, and which it mentions in its summary.
- **Through the day:** capture in `inbox/inbox.md`; Workflow B for anything concrete.
- **When you want your bearings:** "give me the picture" → reads the registers, summarizes.
- **When the inbox fills up** (a line or a note in `inbox/`) **:** "triage my inbox".
- **When the board gets blurry:** "review my actions" — states up to date, finished actions filed, reminded waits reviewed.

## Where things live
The only map is the [what-goes-where table](../AGENTS.md#where-information-goes) ("Where information goes"). Two reflexes: an action is only written in its `state/actions.md` register (never in `tasks.md` or `inbox/inbox.md`); what is cold or finished is archived where the [conventions](CONVENTIONS.md#links-handoffs-and-archives) say, on your request.

## Doing real work
Code tasks run against the real repo under `../repos/` + git. A register action is a POINTER to that work, not the work itself. Start the agent from the root so that it sees the memory and the repo, update the action, and log it on the project page in the same session.

## Maintenance gestures for the agent

- **"Process my brain / my inbox / my actions"** means reconciling the brain owner's manual changes: form, ticked boxes and filing of raw material. `inbox` = triage only; `actions` = form and states of the registers; `brain` = full pass. Do not archive along the way, apart from the monthly moves. Summarize precisely what moved.
- **Before emptying a modified, uncommitted inbox** (`inbox/inbox.md` or the other notes of `inbox/`), offer the brain owner a commit of the raw capture alone so that their words stay in the history; run it only on their GO. Then process each line as in Workflow A and leave a short dated line at the bottom of the inbox noting the dispatch.
- **Keep the registers** according to the reported progress: an action ticked from the board (`[x]` + `✅ date`) joins `Done` in its register; a new state is written on the line, a new fact as a dated sub-bullet. An action about a repo points to the real work; the implementation stays in the repo.
- **Maintain the links** whenever a file is created or moved; check with `uv run tools/brain/check-links.py` from the workspace root. A link to another brain is refused (each brain is a trust boundary). Orphan files must be linked or explicitly classified, with no automatic inference that they can be deleted.
- **Capitalize at the right time**: end of a phase, debrief, handoff, an incident of more than 30 minutes or "next time, I will…" are the moments to ask whether there is a lesson. If so, propose a short dated note following the [criteria in the conventions](CONVENTIONS.md#people-notes-and-voice); do not create an empty note or change the Voice section of `me/about-me.md` without a proposal.
- **Month change** (without asking): move the entries of past months to `journal/YYYY-MM.md` and run `uv run tools/brain/action.py archive --write`, following the [conventions](CONVENTIONS.md#sources-state-and-journal); mention it in the summary. Never rewrite a source.
- **End of session**: a short dated entry in the timeline of the project concerned (current month only), with the model in parentheses, written with `uv run tools/brain/timeline.py add` (it first moves past months into `journal/`); actions updated in their register; useful checks; memory commit proposed (files and message), never run without a GO. Flag any unpushed local commit.
