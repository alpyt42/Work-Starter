# Action tool

`tools/brain/action.py` is the only tool that writes to the action registers (`projects/**/state/actions.md`). Agents call it from the command line. The local `tasks-web` interface runs it for each of its writes and imports its code to read. An action is therefore always written the same way:

```markdown
- [ ] **DEM-101** — Owner — Title ⏫ ➕ 2026-10-13 📅 2026-10-20
    - source: [Minutes of 13/10](../sources/2026-10/2026-10-13-cr-demo.md)
    - created: 2026-10-13 14:32
    - updated: 2026-10-14 09:05
    - 14/10: history entry
```

(`cr` in a source file name means meeting minutes: `YYYY-MM-DD-cr-<slug>.md`.) States: `[ ]` to do, `[/]` in progress, `[w]` waiting, `[x]` done, `[-]` cancelled. Sections: `## Open`, `## Done`, `## Cancelled`.

A brain written with the earlier French labels is converted once with `uv run tools/brain/migrate-english.py` (dry run by default, `--write` to apply it).

- **Creation**: `➕ YYYY-MM-DD` on the line (read by the Tasks plugin, which only knows dates) and `created: YYYY-MM-DD HH:MM` as a sub-bullet (Paris time, to the minute, no seconds). Set once, at creation.
- **Update**: `updated: YYYY-MM-DD HH:MM`, rewritten by every change made with the tool (fields, status, adding or removing history).
- **Due date**: `📅 YYYY-MM-DD` on the line when it is known; a nuanced due date ("before…") goes in a `due:` sub-bullet.
- **Closure**: `✅ YYYY-MM-DD` (done) or `❌ YYYY-MM-DD` (cancelled) on the line; the evidence goes in a `done: <evidence>` sub-bullet, or `cancelled: YYYY-MM-DD by <person> — [source](…)`.
- **Group**: an optional label, not a parent task. At most one `#group/<slug>` tag at the end of the title, just before the Tasks emojis: `- [ ] **DEM-097** — Owner — Plan the workshop #group/demo-workshop ➕ 2026-10-12 📅 2026-10-20`. Slug `[a-z0-9]+(-[a-z0-9]+)*`, 40 characters at most; the interface displays it as "Demo workshop". An action without a tag stays valid and is never modified when another field is rewritten. The tag is written with `--group`, not by hand in `--title`.
- The `source`, `created` and `updated` sub-bullets cannot be removed with `history remove`. Actions older than 2026-10-13 do not have these dates: they are not invented.

## Commands

From the Work root; the output is JSON (exit codes: 0 done, 2 invalid request, 3 not found, 4 conflict).

```sh
uv run tools/brain/action.py list --project acme/demo --table
uv run tools/brain/action.py board                    # complete view by project (terminal)
uv run tools/brain/action.py board --write --watch    # agents/tasks-board.md kept up to date (VS Code preview)
uv run tools/brain/action.py show DEM-099
uv run tools/brain/action.py create --project acme/demo --title "Follow up with the contact" \
    --owner Owner --source "[Minutes of 13/10](../sources/2026-10/2026-10-13-cr-demo.md)" --due 2026-10-20
uv run tools/brain/action.py update DEM-099 --state done --closed-on 2026-10-14
uv run tools/brain/action.py update DEM-099 --group demo-workshop   # --group "" removes the group
uv run tools/brain/action.py history add DEM-099 --text "followed up by mail" --date 2026-10-14
uv run tools/brain/action.py history edit DEM-099 --index 3 --text "followed up by mail and chat"
uv run tools/brain/action.py history remove DEM-099 --index 3
uv run tools/brain/action.py move DEM-099 --to acme/other-mission
uv run tools/brain/action.py check                    # register format (exit code 1 on error)
uv run tools/brain/action.py delete DEM-099
uv run tools/brain/action.py sweep --write            # puts each action under the section of its state
uv run tools/brain/action.py archive --write          # archives closures older than 30 days
uv run tools/brain/action.py sweep --archive --write  # both, sweep first
```

- `--project` accepts the register path, the project folder, `client/mission`, the name of an internal project or the board label (`acme / demo`).
- `create`: ID following the highest found in the whole client or project folder, sources included; appended at the end of `Open`; `--source` required; options `--state` (`todo`, `in-progress`, `waiting`), `--priority` (`high`, `medium`, `low`), `--due`, `--scheduled`, `--due-note`, `--group` (group slug), `--prefix` (register still empty).
- `update`: only the given fields change; an empty value clears `--due`, `--scheduled` or `--group` (option absent: group unchanged). A state change files the action in its section; a closure gets `✅`/`❌` with today's date, or `--closed-on` for the date of the evidence; a reopening removes the closing date.
- `--group`: a validated slug (invalid: exit code 2). A `--title` that itself ends with a valid `#group/<slug>` tag is refused (exit code 2): pass the group through `--group`. An invalid, duplicate or mid-title tag stays in the title as is (nothing is lost on rewrite) and `check` reports it. `list --table` shows the group; the JSON of `list` and `show` carries `group`, and `title`/`raw_title` are without the tag. `sweep`, `archive`, `move`, `delete` and `history` move the line as is and keep the tag.
- `history add`: a `DD/MM: text` sub-bullet at the end of the block (`--date` for the date of the event). `history edit --index N --text T` rewrites an entry keeping its date (or `--date`) and its sub-lines. `history remove --index N` deletes it. The rank N is given by `show`.
- `move --to P`: moves the action and its block to another register of the same client or internal project (the ID does not change, relative links are rewritten, a history entry records where it came from).
- `check [--register R]`: blocking errors (malformed action line, duplicate ID across the whole client archives included, invalid date, open action with a closing date, inconsistent closure mark) and warnings (closed without a date, no source sub-bullet, invalid group slug, several `#group/` tags, tag not at the end of the title).
- Every write accepts `--dry-run`, and the `--expect-version` (line) and `--expect-details-version` (block) locks used by the interface.
- `--brain PATH` or `BRAIN_DIR` for another brain; `ACTION_NOW="YYYY-MM-DD HH:MM"` freezes the clock (tests).

## Board (`board`)

Complete, read-only view of all the registers by project: the owner's To do actions (`BRAIN_OWNER` or `owner` in `brain/.data/doctor.json`), the In progress and Waiting actions of everyone, sorted by ID, then the 15 most recent closures. Each line links to its line in the register. `--write [PATH]` also writes the board (default `agents/tasks-board.md`); `--watch` rewrites it when a register changes (VS Code task of the brain, when the folder opens).

## Sweep (`sweep`)

| State | Section |
|---|---|
| `[ ]` `[/]` `[w]` | `## Open` (at the end of the section) |
| `[x]` | `## Done` (most recent closure first) |
| `[-]` | `## Cancelled` (same) |

Cases covered: an action ticked in the Obsidian Tasks board (it stays in Open), a reopened action, an action filed in the wrong closed section. The sweep creates no date, state or ID: a closed action without `✅`/`❌` is moved and reported. It leaves in place, with a warning, an unknown state or an unknown or missing section.

## Archive (`archive`)

A dated `[x]` or `[-]` action, under `## Done` or `## Cancelled`, whose closure is strictly earlier than `today - --days` (30 by default), moves with its sub-bullets to `state/actions-archive-YYYY.md` (year of closure), under the section of its state, most recent closure first. Its ID stays reserved. An ID that is already archived stops that register without writing anything.

Options shared by `sweep` and `archive`: `--dry-run` (default) / `--write` / `--check` (exit code 1 if anything is to be moved), `--register PATH` (repeatable), `--days N`, `--today YYYY-MM-DD` (or `ARCHIVE_TODAY`), `--quiet`.

## Git hooks

Versioned in `tools/machine/hooks/` and installed by `tools/machine/bootstrap.sh` in every brain present; they validate and never write:

- **brain, `pre-commit`**: on an exact copy of the index (what the commit will contain, not the working folder): misfiled actions (`sweep --check`) and format of the staged registers (`check`), dead Markdown links or links to another brain if a `.md` is staged, client names of another brain (`check-no-client.py --brain … --staged`, outside the `allow` list of `.data/brain.json`); then secrets in the staged additions.
- **Work, `pre-commit`**: secrets in the staged additions.
- **Work and brain, `commit-msg`**: Conventional Commits subject (types of `kit/brain/docs/GIT.md`, lowercase, no trailing period, 100 characters at most, warning beyond 72) and no AI mention.
- **Secrets** (`check-staged-secrets.py`): credential file names and added lines that look like a key or token; values are never displayed; `secret-scan: ignore` on the line neutralizes a false positive.

## When the agent uses it

- To create, edit, complete the history of or delete an action: always this tool, never a hand edit of the register.
- When the `brain-clean` doctor reports actions to archive, or at the start of a new month: `archive --write`, without asking if the brain's conventions provide for it. After a pass over the registers: `sweep --write`.

## Guarantees

- Atomic writes; refused if the register changed between the read and the write; the archive is written before the register and restored if the register write fails.
- Line endings and final newline preserved; `sweep` and `archive` are idempotent.
- Symbolic links and anything outside the brain are ignored.
