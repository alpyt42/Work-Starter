# Timeline tool

`tools/brain/timeline.py` is the only tool that writes the `## Timeline` of a project page and its monthly archives (`<project>/journal/YYYY-MM.md`). Agents call it from the command line, so that an event and a month change are always written the same way:

```markdown
## Timeline
Previous months: [2026-09](journal/2026-09.md) · [2026-08](journal/2026-08.md)

- 2026-10-14 — Demo recorded, see [minutes](sources/2026-10/2026-10-14-cr-demo.md) (Sonnet 5)
- 2026-10-02 — Scope agreed (Opus 5.5)
```

A journal file, one per month, holds the entries moved from the page, unchanged and in the same order:

```markdown
# Journal — Demo — 2026-09

[Back to project](../demo.md)

> Journal archive of Demo for September 2026: entries moved from the project page on 2026-10-01. The current month stays on the page.

- 2026-09-28 — Contract signed (Opus 5.5)
- 2026-09-10 — Workshop held, see [notes](../notes/2026-09-10-workshop.md) (Opus 5.5)
```

The rule itself (current month on the page, past months in `journal/`, moved without asking) is in [the conventions](../../kit/brain/docs/CONVENTIONS.md#sources-state-and-journal). The page is `<project folder>/<folder name>.md`; a project is a folder that contains `state/actions.md`.

## Commands

From the Work root; the output is JSON (exit codes: 0 done, 2 invalid request, 3 not found, 4 conflict).

```sh
uv run tools/brain/timeline.py add --project acme/demo --model "Sonnet 5" "Demo recorded and shared with the client"
uv run tools/brain/timeline.py add --project acme/demo --model "Sonnet 5" --date 2026-09-20 "Late event, see [minutes](sources/2026-09/2026-09-20-cr-late.md)"
uv run tools/brain/timeline.py add --project clients/acme --model "Sonnet 5" "Account review held" --dry-run
uv run tools/brain/timeline.py roll                       # dry run on every project page of the brain
uv run tools/brain/timeline.py roll --project acme/demo   # dry run on one project
uv run tools/brain/timeline.py roll --write               # moves the entries of past months
```

- `--project` accepts the same forms as `action.py` (register path, project folder, `client/mission`, name of an internal project, board label), or `clients/<client>` for the client index page `projects/clients/<client>/<client>.md`. Its journals then sit in `projects/clients/<client>/journal/`. An unknown project is exit code 2; a project without its page, exit code 3.
- `add`: `--model` and the text are required, written as `- DATE — TEXT (MODEL)`; `--date` defaults to today (Paris time) and `--dry-run` writes nothing. The entry goes at its date, most recent first, and **above** the entries of the same date. A date in the current month or later stays on the page. A date in an earlier month goes into that month's `journal/YYYY-MM.md` at its date (the file is created if needed) and its relative links get one more `../`; the previous-months line then lists the month.
- `add` first rolls the page: when it holds entries of past months, they move into their journals as `roll --write` would, in the same write, and the result reports them under `rolled` (`moved`, then `months` with `count`, `duplicates`, `journal`, `created`). The convention asks for this without asking the brain owner: mention it in the session summary.
- `roll`: a dry run unless `--write` is given (`--dry-run` is accepted). It moves, for each page, the entries dated before the current month, unchanged and in order, into `journal/YYYY-MM.md`. A new journal gets a title, a back link to the page and the `> Journal archive of …` line; an existing one receives the entries at their dates, without duplicates (an identical line already in the journal is dropped from the page and counted in `duplicates`). Relative Markdown links of a moved entry get one more `../`; URLs, `#anchors`, absolute paths and code spans are left alone. The report gives `checked` (pages read), `total` (entries to move or moved) and, per project, `moved` and the months. Without `--project` it reads every project page and every client index page that has a `## Timeline`; archived projects are left alone.
- The previous-months line (`Previous months: [YYYY-MM](journal/YYYY-MM.md) · …`, most recent first) sits right under `## Timeline` (after the guidance quote of a page copied from a template). It lists the months it already had, the journal files that exist and the months just written. A line found among the entries is moved up; a template placeholder line is replaced. Without any move, `roll` leaves the page untouched.
- Wording: the label of an existing previous-months line (`Previous months:` or the French `Mois précédents :`), the back link and archive line of the project's existing journals, and the order of their title (`Journal — <project> — YYYY-MM` or `Journal — YYYY-MM — <project>`) are kept for what the tool creates; a project with none follows the wording of the other pages and journals of the brain, else English. An existing journal's header is never rewritten.
- Entries are recognised as `- YYYY-MM-DD — …` lines (a real date) plus their indented continuation lines, inside the `## Timeline` section only (a heading inside a code block does not count). Other lines of the section (quote, free text) stay where they are. The seed placeholder `- (no entries yet)` is replaced by the first entry. A page without a `## Timeline` section gets one at its end when `add` needs it.
- `--brain PATH` or `BRAIN_DIR` for another brain than the default brain of Work (see [tools/README.md](../README.md)); `ACTION_NOW="YYYY-MM-DD HH:MM"` freezes the clock (tests).

## When the agent uses it

- To leave a timeline entry at the end of a session or after a source: `add`, never a hand edit. Run `roll` (dry run, then `--write`) on request or when the `brain-clean` doctor reports past months still on a page; `add` already does it for the project it writes in.
- Past months move without asking, and the session summary says what moved. Anything else about archiving waits for an explicit request from the brain owner.

## Guarantees

- Only the `## Timeline` section of the page and the journal files are written; the rest of the page is byte for byte the same. Line endings and the final newline are preserved.
- Atomic writes (a temporary file in the same folder, then a replace): journals first, the page last; everything is restored if one write fails. A file that changed between the read and the write is refused (exit code 4) and nothing is written.
- `roll` is idempotent: a second `--write` finds nothing to move. A symbolic link as page, journal or `journal/` folder is refused.
- Entries must fit on one line (2000 characters at most), with a real date (`YYYY-MM-DD`) and a model name (80 characters at most).
