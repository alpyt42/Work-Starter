# Client repositories to clone

The private catalogue `.data/client-repos.json` versions **only the local paths and the `origin` URLs** of the client repositories. It pins neither a branch nor a commit. Client URLs never go into a personal or public tooling repository: only here, in the private brain.

Format of an entry: `{"path": "repos/<client>/<repo>", "url": "<git-url>"}` in the `repositories` list. The actual state of the catalogue lives exclusively in `.data/client-repos.json`.

If the workspace provides `tools/repos/client-repos.py`, it reads this catalogue:

```bash
uv run tools/repos/client-repos.py list                 # every path and URL
uv run tools/repos/client-repos.py check                # origin + applied author and key, no network
uv run tools/repos/client-repos.py clone <client>       # plain git clone, identity inherited from ~/.gitconfig
```

Before the first clone for a client, register its public key and check the server's host key (see [`GIT.md`](GIT.md)). If a repository changes URL, check the new remote with the client, fix the catalogue, then run `check` again.
