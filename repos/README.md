# repos/ — local code repositories

Code clones live here. Each clone is an independent Git repository; its content is ignored by the `Work` repository. Only this README and `workspaces/README.md` are tracked by `Work`.

## Organization

- `<client-or-topic>/<repo>/`: main work, with one folder per client or topic.
- `personal/`: personal projects.
- `sandbox/`: disposable experiments.
- `workspaces/`: local `.code-workspace` files; see `workspaces/README.md`.

Keep clones shallow and names descriptive in lowercase-kebab. A clone may carry its own `AGENTS.md` and its `CLAUDE.md` pointer; read them before modifying it.

## Client repositories

The private catalog `brain/.data/client-repos.json` holds their URLs. Use `uv run tools/repos/client-repos.py check` to check the clones present and `uv run tools/repos/client-repos.py clone <client>` to recreate them. The URLs, the inventory, the mission facts and the decisions specific to a client stay in the private brain.

Before any remote Git operation, check the Git and SSH identity according to [`tools/machine/GIT-IDENTITY.md`](../tools/machine/GIT-IDENTITY.md) and respect the client's decisions recorded in the brain. Each clone also follows the rules of its own repository.

## Boundaries

Durable code and technical documentation stay in their repository. The relevant brain keeps the context and the links to the repositories; `agents/` receives disposable work and `artifacts/` the deliverables meant for humans. A shared repository must not contain a machine path or a reference to a private local folder.
