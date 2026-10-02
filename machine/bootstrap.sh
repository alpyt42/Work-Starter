#!/usr/bin/env bash
# Prepare a Work checkout without modifying home-directory configuration.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js is required for project skills" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required for workspace checks" >&2; exit 1; }

if [[ ! -d brain/.git ]]; then
  : "${BRAIN_REMOTE:?Set BRAIN_REMOTE to the private brain repository URL}"
  git clone "$BRAIN_REMOTE" brain
fi

mkdir -p repos/personal repos/sandbox repos/workspaces agents artifacts

if node -e 'const l=require("./skills-lock.json"); process.exit(Object.keys(l.skills || {}).length ? 0 : 1)'; then
  npx --yes skills experimental_install
  if ! git diff --quiet -- skills-lock.json; then
    echo "Warning: skill restore changed skills-lock.json; review the diff before any commit." >&2
  fi
fi

uv run machine/sync-house-skills.py
./machine/link-skills.sh
./machine/check-links.sh
echo "Work checkout ready. Local artifacts are not restored by this script."
