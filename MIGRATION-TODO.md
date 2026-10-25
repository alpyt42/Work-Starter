# TODO — Industrialization and migration of Work / Brain

This roadmap turns Work-Starter into a versioned public product and updates the private brains without overwriting their data. It is the planning reference for the migration; the detailed conventions stay in the files it cites.

## Expected outcome

Eventually:

- Work-Starter is the single maintained public source for conventions, tools, templates, schemas and migrations; it ships no skill, each one lives in the brain whose data it touches;
- each brain (`brain/`, `brain-perso/`, `brain-<name>/`) is an independent private repository and a declared trust boundary (`.data/brain.json`), backed up and versioned by its owner;
- a release updates the public base and may propose a structure migration, but never replaces private content;
- installed skills, Obsidian settings, machine paths, caches and secrets stay local;
- a blank brain is created locally from `kit/brain/seed/` (`tools/brain/new-brain.py`): brain-starter and the demo brain no longer exist, and no copy is maintained by hand;
- every update can be verified with a dry run, is reversible on failure, and never commits or pushes.

## Non-negotiable guarantees

- [ ] A release never replaces `brain/me/`, `brain/people/`, `brain/projects/`, `brain/inbox.md`, `brain/inbox/` or the private workflows.
- [ ] A migration never retroactively rewrites an existing source, meeting minutes, note, decision or register without an explicitly documented transformation.
- [ ] No secret goes into Git, even a private one: tokens, passwords, private keys, cookies and credentials stay in the keychain, a secrets manager, the environment or an ignored `.env`.
- [ ] Every upgrade operation starts with a check of both repositories and a preview of the changes.
- [ ] No updater commits, pushes, or modifies the home configuration, SSH or the keychain.
- [ ] A conflict, a local drift of a managed file or an unrecognized migration stops the operation with an actionable diagnostic.

## Architecture decision

### Source of truth

- [ ] Make Work-Starter the single source of truth of the product.
- [x] Drop `brain-starter`: generic conventions live in `kit/brain/` (`AGENTS.md`, `docs/`, `templates/`), and a brain keeps only a short `AGENTS.md` that points to them.
- [x] Remove `examples/brain/`, `tools/machine/demo.sh` and `.kit-options/`; the seed of a new brain is `kit/brain/seed/`, copied once by `tools/brain/new-brain.py`.
- [x] Ship no skill and no personal setting: `skills/`, `skills-catalog.json`, `.obsidian/` and `tools/timesheet/` (Boond, Toggl) are removed; skills live in the brains, Obsidian is set up by hand (`kit/obsidian/README.md`).
- [x] Several brains: each is a trust boundary (`.data/brain.json`) with its own skills (`<brain>/skills/`) and configuration (`.data/work-config.json`); no link or client name from one brain to another (`check-links.py`, `check-no-client.py --brain`, `brain-pre-commit` hook).
- [x] Test that generates a brain from `kit/brain/seed/` and checks its structure and links (`tests/test_new_brain.py`).
- [ ] Run these tests in CI and also check the actions and decisions of the generated brain there.

### Target tree

```text
Work/
├── AGENTS.md, CLAUDE.md              # workspace map, managed
├── work-config.example.json          # public defaults of the skills configuration
├── kit/
│   ├── brain/
│   │   ├── AGENTS.md                 # conventions shared by all brains
│   │   ├── docs/                     # CONVENTIONS, WORKFLOWS, GIT, REPOSITORIES
│   │   ├── templates/
│   │   ├── seed/                     # copied once into a new brain
│   │   ├── schemas/                  # upcoming
│   │   │   ├── v1.md                 # immutable once published
│   │   │   └── v2.md
│   │   └── migrations/               # upcoming
│   ├── obsidian/                     # manual setup guide, tasks-board.css
│   └── manifests/                    # upcoming
├── tools/                            # managed tools (brain/, machine/, repos/, tasks-web/)
│   └── machine/                      # install, update, doctor, hooks
├── tests/
├── brain/                            # default brain, separate private repository
│   ├── .brain/instance.json          # schema version (upcoming)
│   ├── AGENTS.md                     # short pointer to kit/brain/AGENTS.md
│   ├── AGENTS.local.md               # private rules (upcoming)
│   ├── me/
│   ├── projects/
│   ├── people/
│   ├── inbox/
│   ├── skills/                       # skills specific to the brain
│   └── .data/                        # brain.json, work-config.json, state files
├── brain-perso/, brain-<name>/       # other brains, same structure, one private repository each
├── repos/                            # clones, each its own repository
├── artifacts/                        # local, external backup
└── agents/                           # disposable scratch
```

Local and ignored, outside the versioned tree: `.agents/`, `.claude/skills/`, `.obsidian/`, `work-config.local.json`, `skills-lock.json`, `.work-state.json`, `tools/.env`.

## File ownership model

Create a versioned manifest that classifies each path into a single category:

| Category | Owner | Behavior during a release |
|---|---|---|
| `managed` | Work-Starter | Replaced only if it has not drifted locally |
| `generated` | Generator | Regenerated from the defaults and the local configuration |
| `seed` | Instance after creation | Created only if missing, never replaced |
| `migrated` | Instance | Transformed only by an explicit migration |
| `private` | User | Never modified automatically |
| `local` | Machine | Ignored by Git and never published |

- [x] Declare the boundary of each brain in a manifest (`.data/brain.json`: `scope`, `description`, `remote`, `email`, `allow`) and check it (doctor, `check-links.py`, `check-no-client.py`, `brain-pre-commit` hook).
- [ ] Define an ownership manifest schema readable by both humans and machines.
- [ ] Check that a path cannot belong to two incompatible categories.
- [ ] Add a test that fails for any unclassified public file.
- [ ] Add a test that fails if a private or local path appears among the files to replace.
- [ ] Record the checksums of managed files to detect a drift before overwriting.
- [ ] Document the procedure for promoting a useful customization to the public base.

Indicative example:

```yaml
managed:
  - AGENTS.md
  - kit/**
  - tools/**
  - work-config.example.json

generated:
  - .agents/**
  - .claude/skills/**
  - skills-lock.json
  - .work-state.json

seed:
  - brain/me/about-me.md
  - brain/AGENTS.local.md
  - brain/inbox.md
  - brain/tasks.md
  - brain/.data/brain.json

migrated:
  - brain/.brain/instance.json
  - brain/projects/**/state/**

private:
  - brain/me/**
  - brain/people/**
  - brain/projects/**
  - brain/inbox/**
  - brain/skills/**
  - brain/.data/work-config.json

local:
  - .obsidian/**
  - work-config.local.json
  - brain/.data/local-paths.local.json
  - tools/.env
```

## Customization and privacy

### Private and versioned in the brain

These files must be restorable on another machine and benefit from the private Git history:

- [ ] Keep `brain/me/about-me.md` in the private repository; it carries the professional identity, the way of working, the collaboration preferences and the voice.
- [ ] Create `brain/AGENTS.local.md` for the private rules that complement the public base: autonomy, approvals, privacy boundaries and exceptions specific to the organization.
- [ ] Keep `brain/docs/LOCAL-WORKFLOWS.md` for procedures specific to the owner or their organization.
- [ ] Keep in `brain/.data/` the mappings, private catalogs, shared cursors and state needed to avoid reprocessing the same items on several machines.
- [ ] Make `about-me.md` the human source of identity; avoid a second copy of the name, time zone or languages in several files.
- [ ] If a tool needs structured fields, prefer a validated front matter in `about-me.md` or generate the technical state from that source.

### Local and ignored

- [x] Keep `work-config.local.json` for machine-specific choices (disabled skills, replaced third-party entry).
- [ ] Split `.data/local-paths.json` into private logical data (expected brains) and machine-specific paths (input folders).
- [ ] Create `brain/.data/local-paths.example.json`, then generate or ask for an ignored `brain/.data/local-paths.local.json`.
- [x] Keep `.agents/`, `.claude/skills/`, `.obsidian/` (set by hand), caches and generated files out of Git.
- [ ] Add a doctor warning if a file meant to be local becomes tracked by Git.

### Recommended split

```text
brain/me/about-me.md                    private, versioned
brain/AGENTS.local.md                   private, versioned (upcoming)
brain/docs/LOCAL-WORKFLOWS.md           private, versioned
<brain>/.data/brain.json                private, versioned (boundary of the brain)
<brain>/.data/work-config.json          private, versioned (third-party skills, disabled ones)
<brain>/skills/                         private, versioned (skills specific to the brain)
brain/.data/local-paths.json            private, versioned (expected brains; paths to be split)
brain/.data/client-repos.json           private, versioned
<brain>/.data/*-state.json              private, versioned
brain/.data/local-paths.local.json      local, ignored (upcoming)
work-config.local.json                  local, ignored
tools/.env                              secret, ignored
```

## Conventions and immutable documents

- [x] Move the generic conventions out of the private repository, into `kit/brain/`.
- [x] Reduce `<brain>/AGENTS.md` to a short pointer to `../kit/brain/AGENTS.md`, followed only by the rules specific to the brain.
- [ ] Move these rules into `AGENTS.local.md`, read after the base, if the pointer must stay identical from one brain to another.
- [x] Point Obsidian and the tools to the templates managed in Work-Starter (`kit/brain/templates/`).
- [x] Move the product, the kit and the templates to English (labels, statuses, front matter keys, templates, messages); the tools read and write only the English labels, and a brain written with the earlier French labels is converted once with `tools/brain/migrate-english.py` (dry run by default, `--write` to apply).
- [ ] Distinguish current conventions from immutable specifications.
- [ ] Publish each schema under a versioned name (`schemas/v1.md`, `schemas/v2.md`) and never modify a published version.
- [ ] Use Git tags and releases as stable historical references.
- [ ] Record the template version used when a document is created, if this provenance is useful.
- [ ] Apply new templates only to future documents; do not rewrite historical documents.

## Resolved local configuration

The local file must not be a frozen copy of all the default values.

- [x] Public defaults versioned in `work-config.example.json`, maintained by the releases.
- [x] Limit `work-config.local.json` to the choices and overrides of the machine.
- [x] Resolved configuration = defaults, then each brain's `.data/work-config.json`, then the local override (`work_config.py`); generated files stay ignored: `skills-lock.json` and `.work-state.json` (fingerprint of the resolved configuration).
- [ ] Define the security keys that cannot be overridden.
- [ ] Evolve the configuration schema (`version: 1` in place, unknown keys rejected) and provide its migrations.
- [x] Report installed skills that are unknown (`doctor.py`, `work_config.py adopt`) and a configuration changed since the last `update.sh`.
- [ ] Report keys that became obsolete and skills removed from a layer.
- [x] `work_config.py check` (validation) and `status` (change since the last `update.sh`).
- [ ] Plan `work config diff` and a unified `work config` command.

## Skills and plugins

### Brain skills

- [x] No skill in the starter: the source of an own skill is `<brain>/skills/<name>/`, in the brain whose data it touches.
- [x] Materialize the Codex and Claude discovery points locally (`link-skills.sh`, `sync-house-skills.py`, `.install-as-copy` marker).
- [x] Never expose a disabled skill (`skills.disabled`, union of all layers).

### Third-party skills

- [x] Each entry carries `source`, `sourceType`, `skillPath` and `computedHash` in a brain's `.data/work-config.json` (`adopt` after `npx skills add`).
- [ ] Complete each entry with the exact Git commit and the license.
- [ ] Pin the version of the installation tool called by `npx`.
- [x] Generate the local lock only from the configuration layers (`work_config.py lock`, which refuses unknown skills).
- [ ] Refuse an installation whose content does not match the expected hash.
- [ ] Show the skills added, removed or modified before installation.
- [x] Keep the installed copies out of Git.

### Obsidian

- [x] The starter no longer manages `.obsidian/`: it is ignored and set by hand on each machine (`kit/obsidian/README.md`).
- [ ] Check the guide at each release (plugin IDs, settings, action statuses).

## Initialization

- [x] Keep a single install command (`tools/machine/install.sh`).
- [x] Use the canonical seed (`kit/brain/seed/`) to create a new brain (`tools/brain/new-brain.py`, with `--scope`, `--description`, `--remote`, `--email` for its boundary).
- [x] Create a fresh Git history for the brain without giving it a remote.
- [ ] Create only the `seed` files missing from an existing brain (today `new-brain.py` refuses an existing folder).
- [ ] Generate `brain/.brain/instance.json` with the schema version and the originating release.
- [x] Let the owner add and verify their own private remote.
- [ ] Offer a consumer mode where the Work repository keeps Work-Starter as `origin` and stays fast-forward (today `install.sh` renames `origin` to `starter`; update with `git pull starter main`).
- [ ] Document the contributor mode separately, with a fork and an `upstream` remote.

Copying can serve initialization and scaffolds. It must not be the only barrier protecting private data: the ownership manifest remains the authority.

## Updater and migrations

### Current state

Manual update: `git pull starter main` in Work, `git pull` in each brain, then `tools/machine/update.sh`; `doctor.py` reports a configuration changed since the last `update.sh`. No dry run, no migration, no rollback.

### Target interface

```bash
uv run tools/machine/work.py version
uv run tools/machine/work.py update --check
uv run tools/machine/work.py update --dry-run
uv run tools/machine/work.py update --apply
uv run tools/machine/work.py migrate --dry-run
uv run tools/machine/work.py doctor
```

### Preflight

- [ ] Identify the installed Work version, the latest compatible release and the schema of each brain.
- [ ] Check the Git state of Work and of each brain without reading any secret.
- [ ] Refuse a destructive update if the repository concerned is dirty.
- [ ] Detect local unpushed commits and report them without blocking the read-only checks.
- [ ] Verify the provenance and checksums of the release.
- [ ] Compute the complete plan before any write.

### Dry run

- [ ] Show the versions before and after.
- [ ] List the managed files added, modified and deleted.
- [ ] List the generated files that will be regenerated.
- [ ] List each structural migration and its expected effect.
- [ ] Guarantee and display `private data replaced: 0`.
- [ ] Produce a browsable diff.

### Apply

- [ ] Download or extract the release into a temporary directory.
- [ ] Update only the files classified `managed` and without local drift.
- [ ] Run the necessary migrations in version order.
- [ ] Make each migration idempotent or clearly detect that it was already applied.
- [ ] Regenerate the `generated` files from the resolved configuration.
- [ ] Run the checks on links, actions, decisions, configuration and privacy.
- [ ] Restore the initial state if a step fails.
- [ ] Write a local migration report without secrets.
- [ ] Never commit or push automatically.

### Instance version

Create in each private brain:

```json
{
  "schemaVersion": 1,
  "createdWith": "1.0.0",
  "lastMigratedWith": "1.0.0"
}
```

- [ ] Store no personal data in this file.
- [ ] Check that the current kit can read the brain's schema before running a tool.
- [ ] Cleanly block a brain created by an unknown future version.

## Releases

Adopt SemVer:

- `patch`: fix to a convention, template, tool, test or documentation without a schema change;
- `minor`: compatible addition, new template, skill, document type or optional field;
- `major`: incompatible change of structure or format requiring a migration.

Each release must provide:

- [ ] a user-oriented changelog;
- [ ] the brain schema version;
- [ ] the ownership manifest;
- [ ] the necessary migrations;
- [ ] the checksums of the assets;
- [ ] the compatibility and rollback notes;
- [ ] the test results;
- [ ] an immutable tag.

## CI and quality

- [ ] Test a blank installation on the supported platforms.
- [ ] Test the upgrade from each supported version to the latest.
- [ ] Test an update with realistic private content and check that no private file changes.
- [ ] Test the detection of a drift in a managed file.
- [ ] Test the rollback after a failed migration.
- [ ] Test two successive runs of the same migration.
- [ ] Generate a brain from `kit/brain/seed/` and test it in CI.
- [ ] Check the Markdown links, action registers and decisions.
- [ ] Scan the public paths for private names, machine paths and obvious secrets.
- [ ] Check that `git status` shows no generated file after the tests.
- [ ] Produce a clear matrix of the supported Python, Git, Node, Obsidian and operating system versions.

## Delivery phases

### Phase 0 — Stabilize the existing setup

- [ ] Publish the current state as a tested baseline.
- [ ] Add the tags and a changelog.
- [ ] Document the paths currently managed, private, local and generated.
- [ ] Add the reproducibility checks of the third-party skills lock.

**Done when:** a blank installation passes all the checks from a tag.

### Phase 1 — A single source of truth

- [x] Create `kit/brain/`.
- [x] Move the generic conventions and templates there (schemas: upcoming with phase 3).
- [x] Replace brain-starter with `kit/brain/seed/` and `tools/brain/new-brain.py`.
- [x] Remove the `examples/` demo and `tools/machine/demo.sh`.
- [x] Remove the skills, `.obsidian/` and the Boond/Toggl tooling from the starter; each brain carries its skills and its configuration.

**Done when:** no generic convention or structure is maintained by hand in two places.

### Phase 2 — Ownership and customization

- [x] Declare the boundary of each brain (`.data/brain.json`) and check it.
- [ ] Introduce the file ownership manifest.
- [ ] Add `AGENTS.local.md` and the seed template.
- [ ] Separate machine paths from the shared private state.
- [x] Move to `defaults + overrides + resolved config`.

**Done when:** every file is classified and customizations survive a simulated update.

### Phase 3 — Versions and migrations

- [ ] Add `.brain/instance.json`.
- [ ] Define the migration format and their registry.
- [ ] Implement dry run, transactional apply and rollback.
- [ ] Add the cross-version upgrade tests.

**Done when:** a brain on the previous schema migrates to the current schema without any change to its private data beyond the announced transformations.

### Phase 4 — Update experience

- [ ] Provide the `work update` command.
- [ ] Handle the stable channel and, if useful, a preview channel.
- [ ] Add a readable summary, the diffs and the post-update instructions.
- [ ] Simplify the consumer mode and document the contributor mode.

**Done when:** a non-contributing user can install then update Work with two commands and understand exactly what changes.

### Phase 5 — Public industrialization

- [ ] Add a license, a security policy, contribution guidelines and support.
- [ ] Publish GitHub releases with assets and checksums.
- [ ] Add migration documentation for each major version.
- [ ] Measure installations and errors only if this can be done without implicit telemetry or private data.

**Done when:** the project can be used, updated, audited and contributed to without knowledge of the maintainer's environment.

## Deliberately out of scope

- Automatically synchronizing or backing up the artifacts.
- Publishing a brain or any personal data.
- Managing the user's Git identities, SSH keys, cloud accounts or secrets (rules: `tools/machine/GIT-IDENTITY.md`).
- Shipping skills or generating `.obsidian/`: a skill lives in the brain whose data it touches, Obsidian is set up by hand.
- Silently installing a skill or capability that was not selected.
- Automatically transforming historical content only because a template changed.

## Recommended order for the next iteration

1. Write the ownership manifest of the current tree.
2. Introduce `.brain/instance.json` without changing the structure.
3. Split `local-paths.json` between private logical data and machine paths.
4. Implement `update --check` and `update --dry-run` before any apply command.
5. Add the first real migration only after the rollback and the integrity tests are validated.
