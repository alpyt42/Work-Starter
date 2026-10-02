# AGENTS.md — Work workspace

This repository contains portable agent instructions and tools. Reply in the user's language. Keep client names, people, mission facts, credentials, and machine-specific paths out of this repository.

## Find the work

- `brain/` is a separate private repository for context, actions, decisions, people, and skill data. Read `brain/AGENTS.md` before editing it. For client work, start with `brain/projects/clients/<client>/<client>.md`, then the mission page.
- `brain-perso/` is a second, separate private repository (personal GitHub account) for personal meetings and career topics that must not enter `brain/`. Read `brain-perso/AGENTS.md` before editing it. This repository neither tracks nor references its content. `machine/install.sh --brain-perso <url|new>` clones or creates it; `machine/bootstrap.sh` alone does not.
- `repos/` contains code repositories. Read a repository's own `AGENTS.md` before editing it.
- Respect client-specific gate decisions recorded in the private brain. Do not re-propose an option already declined for that client.
- `artifacts/` contains human-readable outputs and received large files. Each output folder has a provenance `README.md`. Its contents are local and are not backed up by this repository.
- `agents/` is disposable scratch. Promote durable information to `brain/`, durable code to a repository, and durable outputs to `artifacts/`.
- Obsidian opens `Work/` as the only vault; `brain/` is read there as a folder, so its `../repos/` and `../artifacts/` links resolve. Only `.obsidian/app.json`, `appearance.json`, `core-plugins.json`, and `templates.json` are tracked (relative Markdown links, updated on move; `repos/` and `agents/` hidden; templates from `brain/templates/`). Other `.obsidian/` files are local UI state and can contain note paths.

## Keep repository boundaries

- Reusable skills and scripts belong in `skills/` and `tools/`. Client-specific data, brand kits, mappings, and cursor files belong in `brain/.data/` or the appropriate local artifact folder.
- Markdown files in `Work/` never cite documents located outside `Work/` (downloads, synced cloud folders, mail attachments): no local path or file name. Web links to OneDrive or SharePoint (`https://…`) may stay for traceability. Copy a document that must stay cited into `artifacts/` with its provenance `README.md` and cite that copy; otherwise describe its provenance in words. Input folders that skills read outside `Work/` belong in `brain/.data/local-paths.json`, not in Markdown.
- Client repository URLs belong only in the private `brain/.data/client-repos.json`. Use `tools/client-repos.py` to list, check, or clone them; never copy those URLs into this personal repository.
- Codex discovers this repository's skills in `.agents/skills/`; Claude discovers them in `.claude/skills/`. Do not create duplicate `.codex/skills/` entries or install these skills globally. `new-project` uses generated local copies, never symbolic links.
- Do not read, print, or copy the contents of `.env`, private keys, or credentials. `tools/.env` is ignored; `tools/.env.example` contains names only.
- Do not edit home-directory configuration, SSH files, cloud configuration, or keychains without explicit user confirmation.
- Never commit or push without a separate explicit request for each action. Stage only paths touched for that action, inspect the staged diff, and use Conventional Commits without AI attribution.
- `machine/check-no-client.sh` is an optional manual scan for names already listed in the private brain. It does not certify that a file is safe to publish; review the files and staged diff yourself.

## Git and SSH identity per repository

- Keep SSH private keys outside repositories with owner-only file permissions. Use a distinct, passphrase-protected key for each trust boundary (personal, employer, client); prefer a repository-scoped key with the minimum access required when the host supports it. Do not create, register, rotate, or revoke a key without an explicit request. Never inspect or copy key material.
- Author and key are chosen once, in the user's home configuration, not in each clone. `~/.gitconfig` sets `user.useConfigOnly = true` (no global identity, so Git refuses to commit where no rule applies) and includes one `~/.gitconfig-<boundary>` file per trust boundary: by folder with `includeIf "gitdir:…"`, and by remote URL with `includeIf "hasconfig:remote.*.url:…"`, which also applies during `git clone`. The template is `machine/gitconfig.example`. The user's actual mapping lives in the private brain.
- Where a host serves a single account, `~/.ssh/config` picks the key for that host (`IdentityFile`, `IdentitiesOnly yes`). Where a host serves several accounts (for example `github.com`), the boundary file pins the key with `core.sshCommand = ssh -i <key> -o IdentitiesOnly=yes`. Never rely on whichever key an SSH agent offers first. Git authorship and SSH authentication are separate: verify both. Never put key paths, account names, or machine-specific SSH commands in tracked files.
- Do not add a local `user.*` or `core.sshCommand` to a clone: it silently overrides the home rules. Allowed exception: a documented, repository-specific setting such as a verified `UserKnownHostsFile`. Do not disable host-key checks or send passwords in URLs.
- Verify the server's host-key fingerprint against a trusted source before first use. Use an already verified `known_hosts` entry or a repository-local, untracked `.git/known_hosts` selected through `UserKnownHostsFile`. Never trust `ssh-keyscan` output alone or use `StrictHostKeyChecking=no`, `accept-new`, or an empty known-hosts file as a shortcut. Stop and verify any changed host key.
- Before any remote write, check the remote URL and the effective `user.name`, `user.email`, and `core.sshCommand` with their origin (`git config --show-origin --get-regexp '^(user|core\.sshcommand)'`): each value must come from the expected `~/.gitconfig-<boundary>`, not from the clone or another boundary. Check that `GIT_SSH_COMMAND` or `GIT_SSH` does not override them. Test the SSH identity against the host and check the account it reports; use `git ls-remote` to verify repository access. Stop on any mismatch. A single `core.sshCommand` applies to every SSH remote and submodule in that clone, so arrange separate verified identities before using multiple hosts or accounts.
- Before a first clone, make sure a home rule (folder or remote URL) covers the destination; `tools/client-repos.py check` reports the effective author and key of every clone. Changing `~/.gitconfig`, `~/.gitconfig-*`, `~/.ssh/config`, or the SSH agent requires explicit user confirmation.

## Workflows

- Run Python scripts with `uv run <script>`; do not invoke `python` or `python3` directly.
- `machine/install.sh` is the one-command setup after cloning `Work`: it clones or creates `brain/` (and optionally `brain-perso/`), then runs `bootstrap.sh`.
- `machine/bootstrap.sh` creates local directories, clones the private brain when configured, restores project skills, and checks links. It never restores local artifacts.
- Several brains can coexist (`brain/`, `brain-perso/`, any `brain-*/` with `AGENTS.md` and `.data/`). Each item of skill state (a transcript, for example) belongs to one brain only. `uv run tools/brain-state.py` merges their states; `brain/.data/local-paths.json` holds the shared input folders and the `brains` expected on every machine.
- `machine/update.sh` refreshes project skills and reports Git state. It does not commit or push.
- Scripts that write to an external service require an explicit request for that specific operation. The timesheet workflow only reads Toggl and proposes values for manual entry.
- After code work, update the relevant mission page and kanban in `brain/`, leaving a short dated entry and outstanding work. Do not copy code into memory.
