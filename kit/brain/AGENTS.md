# AGENTS.md — Brain memory

The memory is the index of the brain owner's work; the repos are the territory. Plain Markdown, relative links with the `.md` extension, private Git repository. Reply in the owner's language; what people write stays in their language, while folder names and structural keywords stay in English. These conventions apply to every brain of the workspace (`brain/`, `brain-perso/`, `brain-*/`) and are managed by Work in `kit/brain/`; each brain's own `AGENTS.md` keeps only its own rules. Also read the `AGENTS.md` at the workspace root before any change. Unless stated otherwise, the paths below start at the brain root.

## Get oriented before writing

- For tasks: the `state/actions.md` registers are the source of truth; `tasks.md` gathers the daily focus, the per-project list and the kanban, and is not read as a data file. Outside Obsidian: `uv run tools/brain/action.py board` in a terminal, or `uv run tools/tasks-web/tasks-web.py` for the local interface.
- For a client: `projects/clients/<client>/<client>.md`, then `missions/<mission>/<mission>.md`, and only the useful files of `state/`, `workstreams/` or `sources/`. For the brain's own tooling: `projects/internal/setup/setup.md`. For a person: `people/<first-last>.md`.
- Before drafting in the brain owner's name, read the Voice section of `me/about-me.md`, pick its register, deliver a draft in a code block and never send anything without an explicit request.

## Source of truth

- **Historical fact:** the dated source (meeting minutes, mail, team message) says what was said or sent; on its own it does not give the current status.
- **Action:** `state/actions.md` is the only place where an action is written: ID, owner, due date, status, source and history. The line keeps the ID, owner, title and Tasks metadata; nuances, source, the `created` and `updated` timestamps and the history go in sub-bullets. Every action write goes through `uv run tools/brain/action.py`. States: `[ ]` to do, `[/]` in progress, `[w]` waiting, `[x]` done, `[-]` cancelled. Dated evidence is required to close an action; a box ticked by the brain owner in the board counts as evidence. When the two disagree, ask and leave the gap visible.
- **Decision:** `state/decisions.md` carries the status and the source; it is written with `uv run tools/brain/decision.py` (`propose`, `accept`, `reject`, `supersede`). A decision mentioned in a meeting stays proposed until the brain owner has confirmed how it is filed; keep a trace of rejected or superseded decisions.
- **Person:** `people/` is the source of truth for identity and aliases; the mission keeps the person's own role there. Never create a person page without a first and last name, and never invent a fact. Every addition cites a dated source or dated information from the brain owner.

## Where information goes

**A project is a folder that contains `state/actions.md`**: for a client, the mission folder (`projects/clients/<client>/missions/<mission>/`); for internal work, `projects/internal/<project>/`. Only the `clients` and `internal` axes exist in this starter. Each project has its page `<project>.md` and `state/`; `notes/`, `journal/`, `workstreams/`, `sources/YYYY-MM/`, `handoffs/` and `scripts/` are created when needed. A client folder contains only `<client>.md`, `missions/` and, when needed, `archive/`. The table below is the only "what goes where" map; the detailed formats are in [`kit/brain/docs/CONVENTIONS.md`](docs/CONVENTIONS.md).

| Information | Where | Naming | Key rule |
|---|---|---|---|
| Action | `<project>/state/actions.md`; without a mission, `projects/internal/setup/` (`SET`) | `**<ID>**`, project prefix | The only place where an action is written |
| Decision | `<project>/state/decisions.md` | Proposed · Accepted · Rejected / superseded | Proposed until the brain owner has filed it |
| Glossary | `<project>/state/glossary.md` | — | Optional: terms, acronyms, transcription errors |
| Dated source | `<project>/sources/YYYY-MM/`, listed in `index.md` | `YYYY-MM-DD-<type>-<slug>.md` | What a third party said or sent; never rewritten, dated addendum instead |
| Working note | `<project>/notes/` | `YYYY-MM-DD-<topic>.md` | The brain owner's idea, analysis or preparation; editable |
| Reusable lesson, machine config | `projects/internal/setup/notes/` | `YYYY-MM-DD-<topic>.md` | Criteria in the conventions; a lesson from a single mission stays in its own `notes/` |
| Mission reference doc | `<project>/workstreams/` | `<topic>.md`, never dated | Kept up to date |
| Event of the month | `## Timeline` of `<project>.md` | `- YYYY-MM-DD — … (model)` | One line per event, current month only |
| Past months | `<project>/journal/` | `YYYY-MM.md` | Moved without asking; a late event goes in the journal of its month |
| Actions closed for more than 30 days | `<project>/state/` | `actions-archive-YYYY.md` | Moved without asking; IDs stay reserved |
| Handoff | `<project>/handoffs/` | `YYYY-MM-DD-handoff-<slug>.md` | Self-contained |
| Script that builds a deliverable | `<project>/scripts/<topic>/` | `README.md` required | No generated file or secret in Git |
| Profile and voice | `me/about-me.md` | — | Read by the agent; changed only after a proposal |
| Person | `people/`, flat | `first-last.md` | Confirmed first and last name |
| Raw capture | `inbox/inbox.md` | — | Emptied by triage; formerly `inbox.md` at the brain root |
| Raw note to process | `inbox/` | `YYYY-MM-DD-<slug>.md` | Default for any note without a project; deleted after dispatch |
| Content from another scope | the other brain, chosen from its `description` (see [Several brains](#several-brains)) | — | Do not mix scopes |
| Deliverable shown to someone | `../artifacts/` | folder + provenance `README.md` | No `build/` in the brain |
| Scratch, intermediate builds | `../agents/` | — | An agent deletes only what it created in the session |
| Code and technical documentation | `../repos/` | — | The page points, it does not copy |

- **Monthly moves, without asking.** As soon as an agent writes in a project in a new month, or the `brain-clean` doctor reports it, it moves the timeline entries of past months into `journal/YYYY-MM.md`, runs `uv run tools/brain/action.py archive --write` and mentions it in its summary. Any other archiving waits for an explicit request from the brain owner.
- The conventions and guides are in `kit/brain/docs/`, the templates in `kit/brain/templates/` (`../kit/brain/` from a brain); they never receive a project note, and a brain's own `docs/` keeps only `LOCAL-WORKFLOWS.md`. Every new page starts from `kit/brain/templates/_<TYPE>-TEMPLATE.md`. `kit/brain/templates/templater/` holds Templater commands, not page templates to copy.
- Meeting minutes (CR) go through `cr-reunion`, messages through `veille-messages`, and the triage of `inbox/` (the scratchpad `inbox/inbox.md` and the notes next to it) through `inbox`, each with its validation step. When the filing is uncertain, put the question in `inbox/inbox.md`.
- No Markdown file cites a document located outside the workspace: no local path, no file name. Web links may stay for traceability. Copy a document that must stay cited into `../artifacts/` with its provenance README; otherwise describe its provenance in words. The input folders of the skills live in `.data/local-paths.json`.
- Do not ingest secrets.
- Never delete anything in `../artifacts/`; in `../agents/`, delete only what you created in the same session. The brain owner alone removes the rest; moving a file into an `archive/` folder inside them is allowed.
- In Obsidian, the brain is read from the vault opened at the workspace root; do not create a `brain/.obsidian/` vault.
- Links are relative Markdown links with the `.md` extension, no wikilinks. After a move, repair the backlinks and run `uv run tools/brain/check-links.py` from the workspace root.

## Several brains

- Each brain (`brain/`, `brain-perso/`, `brain-<name>/`) is a separate private Git repository and a trust boundary, declared in `.data/brain.json`: `scope` (personal, employer, client…), `description` (what it contains and must never contain), `remote` and `email` (`fnmatch` patterns checked by the machine doctor), and `allow` (names of clients of another brain that may appear in it). Each brain can have its own private skills (`skills/<name>/`) and its own config (`.data/work-config.json`). The default brain (the one named by `"defaultBrain"` in the ignored `work-config.local.json` of the workspace, else `brain/`, else the only brain) also carries the person's settings (`.data/local-paths.json`: expected brains, input folders).
- Before writing new content, read the `description` of each brain (`uv run tools/brain/brain-state.py brains` lists them with their `scope`) and choose the brain from it. If the content fits two brains, or none, ask the brain owner.
- No Markdown link from one brain to another, and no client name of another brain (folders of its `projects/clients/`) in the content, except those in `allow`. `check-links.py` and the brain's pre-commit hook refuse both.
- A skill's state is written in the `.data/` of the brain being written to, never in that of another.

## Finish the work

- Leave a short dated entry in the project's timeline, current month only, with the model in parentheses; update the action in its register. A session must leave a useful trace without copying the sources.
- Check the links, the diff and the Git state. Flag any changes already present at the start and do not overwrite them. **No commit or push without a separate explicit request**: propose the files and a Conventional Commits message; flag unpushed local commits. Never read a `.env` or add an AI mention to a commit or a PR. The brain stays private.

## References to open when needed

- [`kit/brain/docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — formats of sources, registers, decisions, timelines, journal, notes, people, handoffs and archives; the `tasks` board.
- [`kit/brain/docs/WORKFLOWS.md`](docs/WORKFLOWS.md) — inbox triage, reconciliation, capitalization and end of session.
- `docs/LOCAL-WORKFLOWS.md`, in the brain — private paths and local exceptions.
- [`kit/brain/docs/REPOSITORIES.md`](docs/REPOSITORIES.md) — private client Git URLs, remote checks and reproducible cloning.
- [`kit/brain/docs/GIT.md`](docs/GIT.md) — commit format, file selection, remotes and rules for shared repos; read it before any Git operation that writes or publishes.
- `brain-clean` — overall audit or cleanup of the brain, with the brain owner deciding on ambiguities.
