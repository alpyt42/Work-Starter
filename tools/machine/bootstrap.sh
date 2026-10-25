#!/usr/bin/env bash
# Prepare a Work checkout without modifying home-directory configuration.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required for workspace checks" >&2; exit 1; }

# The private brain is cloned only when the workspace has no brain at all (the default brain may be named brain-<name>).
brains="$(uv run tools/machine/work_config.py list-brains)"
if [[ -z "$brains" ]]; then
  : "${BRAIN_REMOTE:?Set BRAIN_REMOTE to the private brain repository URL}"
  git clone "$BRAIN_REMOTE" brain
  brains="$(uv run tools/machine/work_config.py list-brains)"
fi

# Git hooks (local to each clone, so they are installed here): secrets and message checks in Work,
# action sections, links, secrets and message checks in every brain.
install -m 755 tools/machine/hooks/work-pre-commit .git/hooks/pre-commit
install -m 755 tools/machine/hooks/commit-msg .git/hooks/commit-msg
while IFS= read -r brain; do
  if [[ -n "$brain" && -d "$brain/.git" ]]; then
    mkdir -p "$brain/.git/hooks"
    install -m 755 tools/machine/hooks/brain-pre-commit "$brain/.git/hooks/pre-commit"
    install -m 755 tools/machine/hooks/commit-msg "$brain/.git/hooks/commit-msg"
  fi
done <<< "$brains"

mkdir -p repos/personal repos/sandbox repos/workspaces agents artifacts

# Skills: validate the configuration, write the lock, install the third-party skills, expose everything.
uv run tools/machine/work_config.py check
uv run tools/machine/work_config.py lock
if [[ -n "$(uv run tools/machine/work_config.py list-third-party)" ]]; then
  command -v npx >/dev/null || { echo "Node.js (npx) is required for third-party skills" >&2; exit 1; }
  npx --yes skills experimental_install
fi

uv run tools/machine/sync-house-skills.py
./tools/machine/link-skills.sh
./tools/machine/check-links.sh
uv run tools/machine/work_config.py stamp
echo "Work checkout ready. Local artifacts are not restored by this script."
