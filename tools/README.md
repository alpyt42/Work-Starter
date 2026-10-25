# Tools

Reusable scripts of the workspace, organized by domain. Every command runs from the root of `Work/` with `uv run`. The scripts find the root of `Work/` from their own location (`WORK_DIR` and `BRAIN_DIR` variables to point elsewhere).

Shared local configuration, ignored by Git, which stays at the root of this folder: `.env` (optional tokens, created from [.env.example](.env.example); no shipped tool needs one for now). Never read, copy or cite it.

## Memory (brains)

The tools act on the default brain, or on another brain with `BRAIN_DIR` (`--brain` for `action.py` and `decision.py`); `new-brain.py`, `brain-state.py` and `check-links.py` also know the `brain-<name>` brains. The default brain is the one named by `"defaultBrain"` in the ignored `work-config.local.json`, else `brain/`, else the only brain at the root (`uv run tools/machine/work_config.py default-brain`); it is what lets the default brain folder be renamed, for example `brain-<name>`.

| Command | Role | Guide |
|---|---|---|
| `uv run tools/brain/new-brain.py <folder> [--scope S] [--description D] [--remote PATTERN] [--email PATTERN] [--no-git]` | Creates a blank brain (`brain` or `brain-<name>`) from `kit/brain/seed/`: refuses to overwrite an existing folder, runs `git init` (unless `--no-git`), with no commit and no remote. The four options fill in the brain's boundary in `.data/brain.json` | script header |
| `uv run tools/brain/check-links.py [--allow-missing-local]` | Checks that every Markdown link of a brain points to an existing file; a link to another brain fails even if the target exists; `--allow-missing-local` reports separately the targets missing from `artifacts/` and `repos/`; the templates in `skills/<name>/assets/` are not checked | script header |
| `uv run tools/brain/brain-state.py brains` | Lists the brains present (the default brain first) with their `scope`, their `description` and the transcripts they track | script header |
| `uv run tools/brain/brain-state.py transcripts [--new \| --where <file>]` | Merges the transcript states of every brain; `--new`: those that no brain tracks; `--where`: the brain that owns a file | script header |
| `uv run tools/brain/action.py board` | Prints the action registers by project in the terminal (`--write` for a Markdown preview, `--watch` to keep it up to date) | [action.md](brain/action.md) |
| `uv run tools/brain/action.py <command>` | Creates, reads, edits, completes the history of and deletes actions (agents and tasks-web), files the registers by status (`sweep`) and archives closures older than 30 days (`archive`) | [action.md](brain/action.md) |
| `uv run tools/brain/decision.py <command>` | Lists, proposes, accepts, rejects or supersedes the decisions of the `state/decisions.md` registers | [decision.md](brain/decision.md) |
| `uv run tools/brain/migrate-english.py [--brain PATH] [--diff] [--write \| --check]` | Converts a brain written with the earlier French format labels (registers, project and person pages, `tasks.md`, `.data` values) to the English ones, without touching written content; dry run by default, `--write` applies, `--check` exits with code 1 if something is left to convert | script header |

## Local interface (`tasks-web/`)

| Command | Role | Guide |
|---|---|---|
| `uv run tools/tasks-web/tasks-web.py [--port N] [--brain DIR]` | Local web interface for actions (Today, Actions, Board, Notes, Search, Tools, Git) on `http://127.0.0.1:8765/`; a selector at the top left switches between the brains of the workspace without a restart (`?brain=<name>`, `GET /api/brains`; `--brain` sets the default brain); the Tools view runs predefined commands (links, brains, transcripts, actions, repositories) | [README.md](tasks-web/README.md) |
| `./tools/tasks-web/build-dock-app.sh` | Builds the macOS "Actions Brain" app to put in the Dock (macOS) | [README.md](tasks-web/README.md) |
| `tools/tasks-web/launcher.sh` | Launcher called by the app: starts the server if needed and opens the page | [README.md](tasks-web/README.md) |

## Repositories (`repos/`)

| Command | Role | Guide |
|---|---|---|
| `uv run tools/repos/client-repos.py list [<client> \| repos/<client>/<repo>]` | Lists the repositories of the private catalog `.data/client-repos.json` of the default brain | script header |
| `uv run tools/repos/client-repos.py check [<client> \| repos/<client>/<repo>]` | Compares the clones present with the catalog (`origin` URL) and shows the effective author and key of each one, without network | script header |
| `uv run tools/repos/client-repos.py clone <client> [--identity KEY --author-name N --author-email E]` | Clones a client's repositories; a plain `git clone`, the author and key come from `~/.gitconfig`; the three options are a one-off override | script header |

## Machine (`machine/`)

Installation, update, Git hooks and checks of the workspace on a machine: see [machine/README.md](machine/README.md). The Git and SSH identity per trust boundary is detailed in [machine/GIT-IDENTITY.md](machine/GIT-IDENTITY.md).

| Command | Role | Guide |
|---|---|---|
| `tools/machine/install.sh [--brain URL] [--brain-perso URL\|new] [--no-bootstrap]` | Entry point after the clone: clones or creates `brain/` (and `brain-perso/`), then runs `bootstrap.sh` | [README.md](machine/README.md) |
| `tools/machine/bootstrap.sh` | Prepares a fresh checkout: local folders, Git hooks of Work and of every brain, skills, links, checks | [README.md](machine/README.md) |
| `tools/machine/update.sh` | Regenerates skills and links from the configuration, records the configuration fingerprint and reports the Git state of Work and of every brain | [README.md](machine/README.md) |
| `uv run tools/machine/work_config.py <command>` | Skill configuration (`check`, `list-brains`, `default-brain`, `list-own`, `list-third-party`, `list-catalog`, `lock`, `adopt [--brain B]`, `stamp`, `status`) | [README.md](machine/README.md) |
| `uv run tools/machine/doctor.py` | Read-only local diagnosis of the workspace, the brains and their boundaries | [README.md](machine/README.md) |
| `tools/machine/check-links.sh` | Checks the configuration, the skill links and copies and the Markdown links of every brain | [README.md](machine/README.md) |
| `tools/machine/check-no-client.sh [--staged \| --worktree]` | Optional manual scan for the client and person names known to the default brain | [README.md](machine/README.md) |
