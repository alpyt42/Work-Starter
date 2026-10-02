# Work

Portable configuration for a `Work/` workspace. This repository contains instructions, reusable skills, scripts, and setup checks. It contains no client memory, deliverables, credentials, or code clones.

## Layout

| Path                                                     | Role                                    | Git ownership                     |
| -------------------------------------------------------- | --------------------------------------- | --------------------------------- |
| `skills/`, `tools/`, `machine/`, `.kit-options/` | Reusable instructions and tools         | This repository                   |
| `brain/`                                               | Context and skill data                  | Separate private repository       |
| `brain-perso/`                                         | Personal context (optional)             | Separate private repository       |
| `repos/`                                               | Code clones                             | Each clone has its own repository |
| `artifacts/`                                           | Human-readable outputs and large inputs | Local files, ignored              |
| `agents/`                                              | Disposable scratch                      | Local files, ignored              |

The rule README files in `repos/`, `artifacts/`, and `agents/` are tracked. Their working contents are ignored. `artifacts/` is an ordinary local directory: there is no cloud link or automatic restore on a new machine.

## Set up a new machine

**Quick start.** Configure Git and SSH identities first (step 1 below), clone this repository, then let `machine/install.sh` prepare the brains and run `bootstrap.sh`:

```bash
git clone https://github.com/alpyt42/Work-Starter.git ~/Work
~/Work/machine/install.sh --brain <private-brain-git-url>
```

Without `--brain`, a blank brain is created from [brain-starter](https://github.com/alpyt42/brain-starter) (fresh history, no remote). `--brain-perso <url|new>` adds the optional personal brain, and `--help` lists all options. The `origin` remote pointing to Work-Starter is renamed `starter`, so you can add your own; get later starter updates with `git pull starter main`. Work-Starter and brain-starter are public and read-only for everyone but their owner: clone, pull, or fork them, but changes are never pushed back. The script never touches home configuration, never commits or pushes, and can be rerun safely. Or do it by hand:

1. Configure Git and SSH identities yourself, outside this repository: one `~/.gitconfig-<boundary>` per trust boundary, included from `~/.gitconfig` by folder and by remote URL (template: `machine/gitconfig.example`), and one `Host` block per single-account host in `~/.ssh/config`. Check a folder with `git -C <path> config --show-origin --get-regexp '^(user|core\.sshcommand)'`.
2. Clone this repository as `Work/` (or copy it with a fresh history) using the Git identity meant for your personal tooling.
3. Create your private brain from [brain-starter](https://github.com/alpyt42/brain-starter) (`https://github.com/alpyt42/brain-starter.git`) and push it to a private remote, then run `BRAIN_REMOTE=<private-brain-git-url> ./machine/bootstrap.sh` from `Work/`. An optional second brain for personal topics goes in `brain-perso/`, built from the same starter.
4. Check that `brain/` is the intended private repository, run `./machine/check-links.sh`, and verify the skills visible to the agents.

`bootstrap.sh` needs Git, Node.js, and `uv`; `uv` runs the Python tools. The brain remote is intentionally not stored in this personal repository. `artifacts/` starts empty on a new machine.

## Skills and data

The six house skills in `skills/` are maintained here. Codex discovers them through local `.agents/skills/`; Claude uses `.claude/skills/` links. Five of them have local Codex links to their versioned sources and tracked Claude links. `new-project` is a real versioned source directory with no symbolic link; bootstrap generates ignored local copies in `.agents/skills/` and `.claude/skills/`. `new-project` has no portable remote source, so it is versioned here rather than listed in the third-party lock. Third-party skills install at project level into ignored `.agents/skills/`; their sources are recorded in `skills-lock.json`. `machine/bootstrap.sh` restores them from that file and creates only the Claude links they need.

The lock records sources and content hashes, but sources without a fixed Git ref can advance upstream. A fresh restore may change a hash; bootstrap reports a lock diff so it can be reviewed before commit.

Client-specific configuration belongs in `brain/.data/`. The reusable scripts expect `boond-mapping.json`, `toggl-projects-plan.json`, `messages-state.json`, `transcripts.json`, and brand folders there when the related workflows are used. Credentials stay in ignored `tools/.env` or process environment.

Client clone URLs are versioned in the private `brain/.data/client-repos.json`. Use `uv run tools/client-repos.py list` to see them, `check` to compare existing `origin` URLs and show each clone's effective author and key, and `clone <client>` to recreate a client's clones. `clone` is a plain `git clone`: author and key come from the home rules of step 1, and the command refuses to clone when no rule gives an author for the destination. `--identity` and `--author-*` remain available for a one-off override written to the clone. The personal repository stores only the generic tool.

## Obsidian

Open `Work/` as the Obsidian vault; `brain/` appears as a folder inside it. The vault creates relative Markdown links with `.md`, updates them when a file moves, hides `repos/` and `agents/`, asks before deleting, and inserts templates from `brain/templates/`. Only `.obsidian/app.json`, `appearance.json`, `core-plugins.json`, and `templates.json` are tracked; the rest of `.obsidian/` is local UI state, which can contain note paths. To track another settings file, add it to the `.gitignore` exceptions after checking its content.

## Checks

Run `./machine/check-links.sh` after moving files. `machine/check-no-client.sh` is an optional manual scan: it compares publishable file names and text with known client and person names from the private brain. It does not detect all confidential information and is not a pre-commit hook. Review the complete diff and staged file list before committing.

No commit or push is performed by setup or update scripts.
