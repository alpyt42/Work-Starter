#!/usr/bin/env bash
# Expose the enabled skills to Codex and Claude: the own skills of every brain
# (<brain>/skills/<name>, linked; copies are made by sync-house-skills.py) and the
# third-party skills of the work configuration (installed in .agents/skills by npx).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "$ROOT/.agents/skills" "$ROOT/.agents/skills-disabled" "$ROOT/.claude/skills"

ensure_link() {
  local link="$1" target="$2"
  # Managed link of the previous layout (house skills in Work/skills/), or into a brain that no longer holds
  # the skill (brain renamed, skill moved to another brain): replaced by the current one.
  if [[ -L "$link" && "$(readlink "$link")" != "$target" ]]; then
    case "$(readlink "$link")" in
      ../../skills/"${link##*/}" | ../../brain/skills/"${link##*/}" | ../../brain-*/skills/"${link##*/}") rm "$link" ;;
    esac
  fi
  if [[ -e "$link" || -L "$link" ]]; then
    [[ -L "$link" && "$(readlink "$link")" == "$target" && -f "$link/SKILL.md" ]] || {
      echo "Conflicting skill path: $link" >&2
      exit 1
    }
  else
    ln -s "$target" "$link"
  fi
}

remove_managed_link() {
  local link="$1" target="$2"
  if [[ -e "$link" || -L "$link" ]]; then
    [[ -L "$link" && "$(readlink "$link")" == "$target" ]] || {
      echo "Unmanaged skill path: $link" >&2
      exit 1
    }
    rm "$link"
  fi
}

# Assignments (not process substitutions) so that a configuration error stops the script.
enabled_own="$(cd "$ROOT" && uv run tools/machine/work_config.py list-own)"
enabled_third_party="$(cd "$ROOT" && uv run tools/machine/work_config.py list-third-party)"
catalog="$(cd "$ROOT" && uv run tools/machine/work_config.py list-catalog)"

# Links that must exist, one "<agent>|<skill>|<target>" per line; any other managed link is removed.
expected=""

while IFS=$'\t' read -r skill brain mode; do
  [[ -n "$skill" ]] || continue
  [[ "$mode" == link ]] || continue
  for agent in .agents .claude; do
    ensure_link "$ROOT/$agent/skills/$skill" "../../$brain/skills/$skill"
    expected+="$agent|$skill|../../$brain/skills/$skill"$'\n'
  done
done <<< "$enabled_own"

while IFS= read -r skill; do
  [[ -n "$skill" ]] || continue
  if printf '%s\n' "$enabled_third_party" | grep -Fqx "$skill"; then
    # Re-enabled while the copy set aside when it was disabled is still there (and nothing reinstalled it): put it back.
    if [[ ! -e "$ROOT/.agents/skills/$skill" && ! -L "$ROOT/.agents/skills/$skill" && -d "$ROOT/.agents/skills-disabled/$skill" ]]; then
      mv "$ROOT/.agents/skills-disabled/$skill" "$ROOT/.agents/skills/$skill"
    fi
    [[ -f "$ROOT/.agents/skills/$skill/SKILL.md" ]] || { echo "Missing installed skill: $skill" >&2; exit 1; }
    ensure_link "$ROOT/.claude/skills/$skill" "../../.agents/skills/$skill"
    expected+=".claude|$skill|../../.agents/skills/$skill"$'\n'
  else
    remove_managed_link "$ROOT/.claude/skills/$skill" "../../.agents/skills/$skill"
    if [[ -d "$ROOT/.agents/skills/$skill" && ! -L "$ROOT/.agents/skills/$skill" ]]; then
      # An older set-aside copy is a regenerable third-party copy: the current one replaces it.
      rm -rf "$ROOT/.agents/skills-disabled/$skill"
      mv "$ROOT/.agents/skills/$skill" "$ROOT/.agents/skills-disabled/$skill"
    fi
  fi
done <<< "$catalog"

# Remove the managed links (into a brain's skills/, into .agents/skills/, or the old ../../skills/ of the
# previous layout) that are no longer enabled: disabled or deleted skill, brain removed.
# Links pointing anywhere else are not ours and stay.
for agent in .agents .claude; do
  for entry in "$ROOT/$agent/skills"/*; do
    [[ -L "$entry" ]] || continue
    name="${entry##*/}"
    target="$(readlink "$entry")"
    case "$target" in
      ../../brain/skills/"$name" | ../../brain-*/skills/"$name" | ../../.agents/skills/"$name" | ../../skills/"$name") ;;
      *) continue ;;
    esac
    printf '%s' "$expected" | grep -Fxq "$agent|$name|$target" || rm "$entry"
  done
done

if [[ -d "$ROOT/.codex/skills" ]]; then
  rmdir "$ROOT/.codex/skills" || { echo "Unmanaged Codex skill paths remain" >&2; exit 1; }
fi
rmdir "$ROOT/.codex" 2>/dev/null || true
