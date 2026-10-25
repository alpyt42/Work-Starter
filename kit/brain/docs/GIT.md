# Git and publishing the brain

Read this before preparing a commit, a push or a remote change. The essential prohibitions stay in [`AGENTS.md`](../AGENTS.md) and in the workspace's `AGENTS.md`.

## Commits

- Conventional Commits: `type(optional scope): subject`, lowercase imperative with no trailing period, about 72 characters. Allowed types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `perf`, `build`, `ci`, `style`, `revert`. The area goes in the scope, never in place of the type. The body explains why, not the list of files.
- The language of the subject follows the repository's history. In the brain: new note or page → `feat(notes):`, `feat(projects):`, `feat(people):`; triage or grooming pass → `chore(brain):`; convention or `AGENTS.md` → `docs(…):`.
- No commit or push without an explicit request from the brain owner, a separate GO for each action. At the end of a session, propose files and a message; flag unpushed local commits. Stage only the paths touched (`git add <paths>`), never `git add -A`. Check `git diff --cached --name-only` before committing; if the index holds the brain owner's work, use `git commit -- <paths>` to include only the paths of the authorized pass.
- Never a secret, `.env`, key or credential in a commit, even in the message. No AI signature in a commit, PR, comment or description. Never `push --force`, `--amend` or rebase of a commit that has already been shared.

## Git identities and SSH keys

One identity (author + SSH key) per trust boundary: personal, employer, each client. It is chosen once in the home configuration, never in each clone: `~/.gitconfig` carries `user.useConfigOnly = true` and includes one `~/.gitconfig-<boundary>` per folder (`includeIf "gitdir:…"`) and per remote (`includeIf "hasconfig:remote.*.url:…"`, which also applies during `git clone`).

Each brain declares in `.data/brain.json` the expected `remote` and `email` (`fnmatch` patterns): the machine doctor compares these patterns with the clone's effective identity. Mappings specific to a machine or an account are not filled in this guide, which the starter manages. Keep them in the brain's `docs/LOCAL-WORKFLOWS.md` if they must be documented in the private brain, with no private key, passphrase or key path.

- A host that serves several accounts (for example `github.com`) imposes its key through `core.sshCommand` in the included file; a single-account host, through a `Host` + `IdentityFile` + `IdentitiesOnly yes` block in `~/.ssh/config`.
- Check a server's host key fingerprint against a trusted source before the first connection; never accept it blindly.
- Never add a local `user.*` or `core.sshCommand` in a clone: it silently overrides the home rules.

Check (none of these commands reads a private key):

```bash
git config --file ~/.gitconfig --list                                    # useConfigOnly and includeIf rules
git -C <clone> config --show-origin --get-regexp '^(user|core\.sshcommand)'
env | grep -E '^GIT_SSH' || echo "no GIT_SSH*"
ssh -G <host> | grep -E '^(identityfile|identitiesonly) '                # key chosen by ~/.ssh/config
ssh -T git@<host>                                                        # authenticated account
```

## Publishing the brain

- The brain holds client context and must stay private; its destination: (to be completed, private remote). Do not copy anything to a public repository without explicit anonymization.
- Publish an initial snapshot with a fresh history.
- The brain's pre-commit hook (`tools/machine/hooks/brain-pre-commit`) refuses a commit that contains a link to another brain or a client name of another brain (outside the `allow` list of `.data/brain.json`), in addition to malformed registers, dead links (a target missing from `artifacts/` or `repos/`, which are local to each machine, is only reported) and secrets. It only validates.

## Shared repos and client clones

- A shared repo stays neutral and self-contained: no machine path (`~/`, `/Users/…`), no pointer to `brain/` or `repos/`, and no context specific to the brain owner. Carry the useful decisions in the repo and cite other repos by URL. Before pushing, search for `brain/`, `~/`, `/Users/`.
- Read `repos/<client>/AGENTS.md` before touching a client clone. In a client clone, a separate GO for commit, push, rebase, remote and `gh`/`glab` operations. No AI signature or local reference in what goes to the client.
