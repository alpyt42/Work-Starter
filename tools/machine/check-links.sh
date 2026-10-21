#!/usr/bin/env bash
# Read-only checks: work configuration, skill links and copies, and the links of every brain.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

uv run tools/machine/work_config.py check
uv run tools/machine/sync-house-skills.py --check

enabled_own="$(uv run tools/machine/work_config.py list-own)"
enabled_third_party="$(uv run tools/machine/work_config.py list-third-party)"
brains="$(uv run tools/machine/work_config.py list-brains)"

while IFS=$'\t' read -r skill brain mode; do
  [[ -n "$skill" ]] || continue
  for agent in .agents .claude; do
    link="$ROOT/$agent/skills/$skill"
    if [[ "$mode" == copy ]]; then
      [[ -d "$link" && ! -L "$link" && -f "$link/SKILL.md" ]] || {
        echo "Missing generated skill copy: $link" >&2
        exit 1
      }
    elif [[ ! -L "$link" || "$(readlink "$link")" != "../../$brain/skills/$skill" || ! -f "$link/SKILL.md" ]]; then
      echo "Missing or broken skill link: $link" >&2
      exit 1
    fi
  done
done <<< "$enabled_own"

while IFS= read -r skill; do
  [[ -n "$skill" ]] || continue
  [[ -f "$ROOT/.agents/skills/$skill/SKILL.md" ]] || { echo "Missing installed skill: $skill" >&2; exit 1; }
  [[ -f "$ROOT/.claude/skills/$skill/SKILL.md" ]] || { echo "Missing Claude skill link: $skill" >&2; exit 1; }
done <<< "$enabled_third_party"

for agent in .agents .claude; do
  for link in "$ROOT/$agent/skills"/*; do
    if [[ -L "$link" && ! -e "$link" ]]; then
      echo "Broken skill link: $link" >&2
      exit 1
    fi
  done
done

[[ ! -e "$ROOT/.codex/skills" && ! -L "$ROOT/.codex/skills" ]] || {
  echo "Obsolete .codex/skills directory remains" >&2
  exit 1
}

# Every brain is checked, even after a failure: the status is accumulated and reported at the end.
status=0
if [[ -z "$brains" ]]; then
  echo "No brain present; memory links were not checked"
else
  while IFS= read -r brain; do
    [[ -n "$brain" ]] || continue
    echo "== $brain =="
    BRAIN_DIR="$ROOT/$brain" uv run "$ROOT/tools/brain/check-links.py" --allow-missing-local || status=1
  done <<< "$brains"
fi
if [[ $status -ne 0 ]]; then
  echo "Memory links check failed" >&2
  exit 1
fi
echo "Skill links OK"
