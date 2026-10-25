# skills/

**Private** skills of this brain: agent procedures that touch its data (meeting minutes, triage, tools specific to the employer or a client). They live here, in the brain's private repository, never in the public starter. The states they produce go in the [`.data/`](../.data/README.md) of this same brain.

A skill = a folder `skills/<name>/`:

- `SKILL.md` — name, description (when to use it) and procedure.
- `scripts/`, `references/`, `assets/` — optional: code, documentation to open at the right time, template files.
- `.install-as-copy` — marker file to add for a skill that must be **copied** to the agent rather than linked to this folder.

Third-party skills (public catalogue) are not copied here: they are listed in [`.data/work-config.json`](../.data/work-config.json) (`skills.thirdParty`) and installed by `tools/machine/update.sh`; `skills.disabled` lists the ones you turn off. To adopt in this brain a skill already present in the workspace: `uv run tools/machine/work_config.py adopt --brain <brain>`.

## Find the Work root from a script

A skill script (`scripts/`) never counts a fixed number of `parents[N]` to reach the workspace root: the skill folder can be moved, and the script also runs through the `.claude/skills/<name>` link. It walks up from `Path(__file__).resolve()` to the first folder that contains `tools/machine/work_config.py` (the Work root; `WORK_DIR`, if set, wins), then derives the brain and `tools/` from it:

```python
import os
import sys
from pathlib import Path

here = Path(__file__).resolve()
found = next((p for p in here.parents if (p / "tools/machine/work_config.py").is_file()), None)
work = Path(os.environ.get("WORK_DIR") or found or sys.exit("Work root not found: set WORK_DIR"))
own = next((p for p in here.parents if (p / "AGENTS.md").is_file() and (p / ".data").is_dir()), work / "brain")
brain, tools = Path(os.environ.get("BRAIN_DIR") or own), work / "tools"
```

The script reads the brain that holds it, whatever its name; a skill installed as a copy (`.install-as-copy`) is outside its brain and falls back to `brain/`. `BRAIN_DIR` overrides both, like the tools in `tools/`; `uv run tools/machine/work_config.py default-brain` prints the default brain of the workspace.
