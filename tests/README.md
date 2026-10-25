# tests/

Tests of the scripts in `tools/`, with no remote service or private data, on temporary `Work/` workspaces: `uv run --with pytest --with markdown-it-py pytest tests/` from the `Work/` root. The interface tests only open an ephemeral port on `127.0.0.1`.

Fictitious names only in tests and fixtures (`acme`, `globex`, `initech`, `brain-acme`…): see the rule in [`AGENTS.md`](../AGENTS.md), « Keep repository boundaries ».

- `test_check_links.py` — brain link check (including links to another brain and the ignored templates of `skills/<name>/assets/`) and `check-links.sh` on several brains.
- `test_gitignore.py` — ignore rules of the root: hidden local files of `tools/` are never tracked.
- `test_claude_bash_guard.py` — the Claude Code hook: direct `python` refused, nothing deleted or moved out of `artifacts/` (except into `artifacts/archive/`), no Git hook bypass.
- `test_preflight_push.py` — checks before a push (identity origin, `GIT_SSH*`, `brain.json` boundary, SSH account with a stub, fast-forward) and the `pre-push` hook through real pushes to a local bare remote.
- `test_client_repos.py` — catalog and cloning of client repositories.
- `test_brain_state.py` — list of the brains (scope, description), merge of the states across brains, and `map` (projects, pages, registers, counts, archived, JSON keys).
- `test_new_brain.py` — creation of a blank brain from `kit/brain/seed/`, its boundary (`.data/brain.json`), its `.gitignore` and the rule of `skills/README.md` for finding the Work root.
- `test_brain_boundaries.py` — boundaries between brains: client names of another brain (`check-no-client.py`), the `brain-pre-commit` hook and the **New action** form; in Work, the names of every brain and the employer name, and the `work-pre-commit` hook.
- `test_action.py`, `test_action_board.py`, `test_decision.py` — registers, views and transitions of actions and decisions.
- `test_timeline.py` — timeline entries at their date, past months rolled into `journal/YYYY-MM.md` (link correction, previous-months line, wording, idempotence).
- `test_migrate_english.py` — conversion of a brain from the French format labels to the English ones (`migrate-english.py`): content untouched, idempotent.
- `test_tasks_web.py` — local interface, API, document search and Git view.
- `test_machine_doctor.py` — machine diagnosis: brains, skill configuration, links and orphan folders of `.agents/skills/`, boundary of each brain.
- `test_work_config.py` — layers of the skill configuration (defaults, brains, local), the default brain (`defaultBrain`, `default-brain`), lock, `adopt`, fingerprint.
- `test_link_skills.py` — `link-skills.sh` and `sync-house-skills.py`: links and copies of skills from several brains, third-party skills (setting aside and re-enabling), cleanup, migration from the old organization.
