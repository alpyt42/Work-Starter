# .data/

Private states and settings of this brain and its skills. Versioned with the brain, never cited in a public tooling repository. No secrets here: tokens go in an ignored `.env` at the workspace level.

| File | Role | Skill or tool |
|---|---|---|
| `brain.json` | boundary of the brain: `scope` (for example `personal`, `employer` or `client`), `description` (what it holds and must never hold), expected `remote` and `email` (`fnmatch` patterns), `allow` (client names of another brain that may appear here) | agents, `brain-state.py brains`, `check-no-client.py`, the machine doctor |
| `work-config.json` | third-party skills to install (`skills.thirdParty`) and disabled skills (`skills.disabled`) | `tools/machine/work_config.py`, `update.sh` |
| `doctor.json` | `owner`: display name of the brain's owner. Read by `tools/brain/action.py` (owner of the board and default owner of new actions) and by `tools/brain/decision.py` (default person who accepts or rejects a decision); also the default owner of the **New action** form | `tools/brain/action.py`, `tools/brain/decision.py` |
| `local-paths.json` | expected brains and input folders outside the workspace, relative to `$HOME` (personal settings of the machine: only the default brain carries them) | `brain-state.py`, `cr-reunion` |
| `transcripts.json` | transcripts already handled, one entry per file: `status` (`processed`, `ignored`, `split`, `duplicate` or `undecided`), `processed_on` (date), `destinations` (where its content went) and `note` | `cr-reunion` |
| `messages-state.json` | cursors and ids of processed messages (`status` of a message: `processed` or `ignored`) | `veille-messages` |
| `client-repos.json` | private catalogue of client Git URLs (see [`kit/brain/docs/REPOSITORIES.md`](../../kit/brain/docs/REPOSITORIES.md)) | `tools/repos/client-repos.py` |

A private skill of this brain ([`skills/`](../skills/README.md)) may add its own state file here; it creates the file itself and declares it in this table. A skill's state is always written in the `.data/` of the brain it writes to.
