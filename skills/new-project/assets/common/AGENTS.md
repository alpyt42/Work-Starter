# AGENTS.md

Instructions for coding agents (Claude Code, Codex) in this repo. This file is the single source of truth; `CLAUDE.md` only imports it.

## Project
- Goal: _one sentence, from SPEC.md_
- Stack: _languages, frameworks, services_
- Layout: _main folders and what they hold_
- Run: _command to start the app_
- Spec and plan: [`SPEC.md`](SPEC.md) (what and why) · [`PLAN.md`](PLAN.md) (slices, in order)

## Working method
- Work one slice of `PLAN.md` at a time: plan it, implement it, run the quality gates, check the app for real, commit, tick it.
- Keep changes small and focused; do not touch unrelated code or add features outside `SPEC.md`.
- Read the current docs of a library (Context7 MCP or official docs) instead of relying on memory.
- Do not add a dependency without saying why.
- Commit after each working slice with Conventional Commits (`feat:`, `fix:`, `test:`…).

## Quality gates
A slice is done only when all of these pass and the app actually runs:

<!-- gates -->

Automatic guards, never bypass or work around them:
- `.agents/hooks/format.sh` formats the changed files after each agent edit.
- `.agents/hooks/guard.sh` blocks access to secrets and destructive or remote git commands (push, reset --hard, clean -f, branch -D, --no-verify): the user runs those.
- Pre-commit runs the linters and checks on every commit.

## Python
- Always `uv` with `pyproject.toml`; commit `uv.lock`. Add: `uv add <pkg>` (`--dev` for tools); run: `uv run <cmd>`.
- Never `pip install`, `requirements.txt`, Poetry, Pipenv or conda.

## Secrets
- Secrets live in a git-ignored `.env`; list the variable names, without values, in `.env.example`.
- Never read, print or copy a `.env`, a key, `~/.ssh` or `~/.aws`, and never dump the environment. Code loads secrets at runtime; the agent never needs their values.

## Skills
- Project skills (written for this repo): `.agents/skills/<name>/` (Codex), plus a symlink `.claude/skills/<name>` -> `../../.agents/skills/<name>` (Claude Code).
- Downloaded skills are installed at project level after the user's OK with `npx skills add <owner/repo> --skill <name> -a claude-code -a codex -y`. Track `skills-lock.json`, not the installed copies.
