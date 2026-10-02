#!/usr/bin/env bash
# Expose project skills to Codex through .agents/skills and to Claude through .claude/skills.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/.agents/skills" "$ROOT/.claude/skills"

ensure_link() {
  local link="$1" target="$2"
  if [[ -e "$link" || -L "$link" ]]; then
    [[ -L "$link" && "$(readlink "$link")" == "$target" && -f "$link/SKILL.md" ]] || {
      echo "Conflicting skill path: $link" >&2
      exit 1
    }
  else
    ln -s "$target" "$link"
  fi
}

remove_old_codex_link() {
  local link="$1" target="$2"
  if [[ -e "$link" || -L "$link" ]]; then
    [[ -L "$link" && "$(readlink "$link")" == "$target" ]] || {
      echo "Unmanaged Codex skill path: $link" >&2
      exit 1
    }
    rm "$link"
  fi
}

for skill in brain-clean brand-deck cr-reunion timesheet veille-messages; do
  [[ -f "$ROOT/skills/$skill/SKILL.md" ]] || { echo "Missing house skill: $skill" >&2; exit 1; }
  ensure_link "$ROOT/.agents/skills/$skill" "../../skills/$skill"
  ensure_link "$ROOT/.claude/skills/$skill" "../../skills/$skill"
  remove_old_codex_link "$ROOT/.codex/skills/$skill" "../../skills/$skill"
done

while IFS= read -r skill; do
  [[ -n "$skill" ]] || continue
  target="$ROOT/.agents/skills/$skill/SKILL.md"
  [[ -f "$target" ]] || { echo "Missing installed skill: $skill" >&2; exit 1; }
  ensure_link "$ROOT/.claude/skills/$skill" "../../.agents/skills/$skill"
  remove_old_codex_link "$ROOT/.codex/skills/$skill" "../../.agents/skills/$skill"
done < <(cd "$ROOT" && node -e 'const l=require("./skills-lock.json"); for(const name of Object.keys(l.skills || {})) console.log(name)')

if [[ -d "$ROOT/.codex/skills" ]]; then
  rmdir "$ROOT/.codex/skills" || { echo "Unmanaged Codex skill paths remain" >&2; exit 1; }
fi
rmdir "$ROOT/.codex" 2>/dev/null || true
