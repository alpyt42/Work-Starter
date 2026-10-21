#!/usr/bin/env bash
# Refresh the skills and report local Git state. Never commit or push.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

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

repos=("$ROOT")
while IFS= read -r brain; do
  if [[ -n "$brain" ]]; then repos+=("$ROOT/$brain"); fi
done <<< "$(uv run tools/machine/work_config.py list-brains)"
for repo in "${repos[@]}"; do
  if [[ -d "$repo/.git" ]]; then
    echo "== ${repo##*/} =="
    git -C "$repo" status --short --branch
    if git -C "$repo" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
      ahead="$(git -C "$repo" rev-list --count '@{upstream}..HEAD')"
      echo "Local commits not pushed: $ahead"
    fi
  fi
done
