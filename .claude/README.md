# .claude/

Claude Code configuration of the `Work/` project.

- `settings.json` — shared settings tracked by Git. It runs `tools/machine/hooks/claude-bash-guard.py` before every Bash command (refuses direct `python`, deletions or moves out of `artifacts/`, and Git hook bypasses); the hook needs `uv`. Personal settings go in `settings.local.json`, which is ignored.
- `skills/` — entirely generated and ignored by Git: links to the skills of the brains (`<brain>/skills/<name>/`) and to the third-party skills installed in `../.agents/skills/`, copies of the skills marked `.install-as-copy`. The starter ships no skill. Regenerate with `tools/machine/update.sh`; edit nothing in it.
