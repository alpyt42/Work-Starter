# AGENTS.md — Work workspace

Portable agent instructions and tools for a `Work/` workspace. Reply in the user's language. Keep client names, people, mission facts, credentials, and machine-specific paths out of this repository: they belong in the private brains.

## Find the work

- `tools/` holds the reusable scripts by domain (`brain/`, `machine/`, `repos/`, `tasks-web/`); `tools/README.md` indexes the commands and `tests/` covers them. This repository ships no skill.
- `kit/brain/` holds what every brain shares, managed here and updated by `git pull starter main`: `AGENTS.md` (conventions), `docs/` (guides), `templates/` (note models), and `seed/` (files copied once into a new brain by `uv run tools/brain/new-brain.py <dir>`). Never place real client or person data in `kit/`. `kit/obsidian/` is the manual Obsidian setup guide.
- `brain/`, `brain-perso/`, and `brain-<name>/` at the Work root are the private memories: context, actions, decisions, people, own skills, and skill state. Each is a separate private Git repository and one trust boundary, declared in its `.data/brain.json`. This repository neither tracks nor references their content. The default brain, the one the tools act on when none is named, is the brain named by `"defaultBrain"` in the ignored `work-config.local.json`, else `brain/`, else the only brain at the root; `uv run tools/machine/work_config.py default-brain` prints it.
- To locate a client, project, page or register, start with `uv run tools/brain/brain-state.py map`: one line per project of every brain (`--brain NAME` for one, `--all` for the archived, `--json` for scripts).
- Before editing a brain, read `kit/brain/AGENTS.md`, then the brain's own `AGENTS.md`. For client work, start with `<brain>/projects/clients/<client>/<client>.md`, then the mission page.
- Several brains: choose the brain from its `description` (`uv run tools/brain/brain-state.py brains`) and ask when the content fits two or none. No link from one brain to another, no client name of another brain (`kit/brain/AGENTS.md`, section « Several brains »).
- `repos/` contains code repositories. Read a repository's own `AGENTS.md` before editing it. Respect client-specific gate decisions recorded in the private brain; do not re-propose an option already declined for that client.
- `artifacts/` contains human-readable outputs and received large files, each folder with a provenance `README.md`. Its contents are local and are not backed up by this repository.
- `agents/` is scratch: an agent removes only what it created in the same session, the owner clears the rest. Promote durable information to the right brain, durable code to a repository, and durable outputs to `artifacts/`.
- Obsidian opens `Work/` as the only vault. `.obsidian/` is ignored and set by hand on each machine (`kit/obsidian/README.md`).

## Skills and configuration

- Own skills live in `<brain>/skills/<name>/` (a `.install-as-copy` marker installs a copy instead of a link). Third-party skills are listed in `<brain>/.data/work-config.json`; install one with `npx skills add <source>`, then record it with `uv run tools/machine/work_config.py adopt [--brain <name>]` (the default brain unless named).
- Configuration layers, the last one winning: `work-config.example.json`, each brain's `.data/work-config.json`, then the ignored `work-config.local.json` for choices that concern one machine (for example disabling a skill, or `"defaultBrain": "brain-<name>"`, which no other layer accepts). `uv run tools/machine/work_config.py check` validates them.
- Codex discovers skills in `.agents/skills/`, Claude in `.claude/skills/`. Both are generated and ignored, like `skills-lock.json` and `.work-state.json`: never edit them, run `tools/machine/update.sh`. Do not create `.codex/skills/` or install skills globally.

## Keep repository boundaries

- Reusable scripts belong in `tools/`. Client-specific data, brand kits, mappings, and cursor files belong in the `.data/` of the brain they concern, or in the appropriate local artifact folder.
- Markdown files in `Work/` never cite documents located outside `Work/` (downloads, synced cloud folders, mail attachments): no local path or file name. Web links (`https://…`) may stay for traceability. Copy a document that must stay cited into `artifacts/` with its provenance `README.md` and cite that copy; otherwise describe its provenance in words. Input folders that skills read outside `Work/` belong in the default brain's `.data/local-paths.json`, not in Markdown.
- Client repository URLs belong only in the default brain's private `.data/client-repos.json`. Use `tools/repos/client-repos.py` to list, check, or clone them; never copy those URLs into this repository.
- Tests, fixtures, examples and docstrings use fictitious names only (`acme`, `globex`, `initech`, `brain-acme`…): never the name of the owner's employer, a client, a person or a real project.
- `tools/machine/check-no-client.sh` scans for the names already listed in the private brains (clients, people, and the employer name); the Work pre-commit hook runs it on the staged files. It does not certify that a file is safe to publish; review the files and staged diff yourself.

## Hard rules

- Write every change to this workspace in English — code, comments, messages, documentation, templates, skills and commit messages — even when the conversation is in another language. Reply to the user in their language. A brain may keep content written in its owner's language (notes, minutes, people pages): edit that content in the language it is written in.
- Never commit or push without a separate explicit request for each action. Stage only paths touched for that action, inspect the staged diff, and use Conventional Commits without AI attribution. The hooks installed by `bootstrap.sh` refuse staged secrets, private names in Work, non-conforming messages, and pushes with the wrong identity, a force push or a remote branch deletion; never bypass them (`--no-verify`). In Claude Code, `.claude/settings.json` also refuses direct `python`, deletions in `artifacts/` and hook bypasses before a command runs.
- Never delete anything in `artifacts/`, even a file you produced. In `agents/`, delete only what you created yourself in the same session (tests, fixtures, intermediate files); never the files of an earlier session, of another agent or of the owner. The only other move allowed is into an `archive/` folder inside them (for example `agents/archive/`, `artifacts/archive/`); the owner removes the rest.
- Do not read, print, or copy the contents of `.env`, private keys, or credentials. `tools/.env` is ignored; `tools/.env.example` contains names only.
- Do not edit home-directory configuration, SSH files, cloud configuration, or keychains without explicit user confirmation.
- Never open or interact with an Internet site to perform an operation on the user's behalf. For online changes, prepare the content or instructions and let the user apply them.
- Before any remote write or a first clone, read `tools/machine/GIT-IDENTITY.md`: how the Git author and SSH key are chosen per trust boundary, and how to verify them.
- Scripts that write to an external service require an explicit request for that specific operation.

## Workflows

- Run Python scripts with `uv run <script>`; do not invoke `python` or `python3` directly.
- `tools/machine/install.sh` is the one-command setup after cloning `Work`: it clones `brain/` or creates a blank one from `kit/brain/seed/` (and optionally `brain-perso/`), then runs `bootstrap.sh` (local directories, Git hooks in Work and in every brain, skills, link checks). It never restores local artifacts.
- Another brain is created with `uv run tools/brain/new-brain.py brain-<name> --scope … --description …`, or cloned by hand with the identity of its own boundary; run `bootstrap.sh` again to install its hooks.
- `tools/machine/update.sh` regenerates the skill installs and links from the configuration and reports the Git state of Work and of each brain. It does not pull, commit, or push.
- `uv run tools/machine/doctor.py` (read-only, no network) reports what is missing or out of date on this machine, including a configuration changed since the last `update.sh` and a brain whose remote or e-mail leaves its declared boundary. `tools/machine/check-links.sh` checks the skill links and the Markdown links of every brain; run it after moving files.
- After code work, update the relevant mission page and action register in the right brain, leaving a short dated entry and outstanding work. Do not copy code into memory.
