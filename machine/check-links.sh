#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

uv run "$ROOT/machine/sync-house-skills.py" --check

for skill in brain-clean brand-deck cr-reunion timesheet veille-messages; do
  for agent in .agents .claude; do
    link="$ROOT/$agent/skills/$skill"
    if [[ ! -L "$link" || ! -f "$link/SKILL.md" ]]; then
      echo "Missing or broken skill link: $link" >&2
      exit 1
    fi
  done
done

while IFS= read -r skill; do
  [[ -n "$skill" ]] || continue
  [[ -f "$ROOT/.agents/skills/$skill/SKILL.md" ]] || { echo "Missing installed skill: $skill" >&2; exit 1; }
  [[ -f "$ROOT/.claude/skills/$skill/SKILL.md" ]] || { echo "Missing Claude skill link: $skill" >&2; exit 1; }
done < <(cd "$ROOT" && node -e 'const l=require("./skills-lock.json"); for(const name of Object.keys(l.skills || {})) console.log(name)')

[[ ! -e "$ROOT/.codex/skills" && ! -L "$ROOT/.codex/skills" ]] || {
  echo "Obsolete .codex/skills directory remains" >&2
  exit 1
}

if [[ -d "$ROOT/brain/.git" ]]; then
  BRAIN_DIR="$ROOT/brain" uv run "$ROOT/tools/check-links.py" --allow-missing-local
else
  echo "brain/ is absent; memory links were not checked"
fi
echo "Skill links OK"
