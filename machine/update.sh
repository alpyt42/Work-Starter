#!/usr/bin/env bash
# Refresh project skills and report local Git state. Never commit or push.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if node -e 'const l=require("./skills-lock.json"); process.exit(Object.keys(l.skills || {}).length ? 0 : 1)'; then
  npx --yes skills update -p
fi

uv run machine/sync-house-skills.py
./machine/link-skills.sh
./machine/check-links.sh
for repo in "$ROOT" "$ROOT/brain"; do
  if [[ -d "$repo/.git" ]]; then
    echo "== ${repo##*/} =="
    git -C "$repo" status --short --branch
    if git -C "$repo" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
      ahead="$(git -C "$repo" rev-list --count '@{upstream}..HEAD')"
      echo "Local commits not pushed: $ahead"
    fi
  fi
done
