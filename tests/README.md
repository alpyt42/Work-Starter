# tests/

Tests of the scripts in `tools/`, with no remote service or private data, on temporary `Work/` workspaces: `uv run --with pytest --with markdown-it-py pytest tests/` from the `Work/` root. The interface tests only open an ephemeral port on `127.0.0.1`.

- `test_check_links.py` — brain link check (including links to another brain and the ignored templates of `skills/<name>/assets/`) and `check-links.sh` on several brains.
- `test_gitignore.py` — ignore rules of the root: hidden local files of `tools/` are never tracked.
- `test_client_repos.py` — catalog and cloning of client repositories.
- `test_brain_state.py` — list of the brains (scope, description) and merge of the states across brains.
- `test_new_brain.py` — creation of a blank brain from `kit/brain/seed/`, its boundary (`.data/brain.json`), its `.gitignore` and the rule of `skills/README.md` for finding the Work root.
- `test_brain_boundaries.py` — boundaries between brains: client names of another brain (`check-no-client.py`), the `brain-pre-commit` hook and the **New action** form.
- `test_action.py`, `test_action_board.py`, `test_decision.py` — registers, views and transitions of actions and decisions.
- `test_migrate_english.py` — conversion of a brain from the French format labels to the English ones (`migrate-english.py`): content untouched, idempotent.
- `test_tasks_web.py` — local interface, API, document search and Git view.
- `test_machine_doctor.py` — machine diagnosis: brains, skill configuration, links and orphan folders of `.agents/skills/`, boundary of each brain.
- `test_work_config.py` — layers of the skill configuration (defaults, brains, local), lock, `adopt`, fingerprint.
- `test_link_skills.py` — `link-skills.sh` and `sync-house-skills.py`: links and copies of skills from several brains, third-party skills (setting aside and re-enabling), cleanup, migration from the old organization.
