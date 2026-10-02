#!/usr/bin/env bash
# Agent hook (PostToolUse, Claude Code and Codex): format the files changed since
# the last commit with the formatter of their stack (ruff, prettier, terraform
# fmt), found from the nearest project root. Never blocks the agent.
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0

nearest() { # nearest <file> <marker>: closest parent dir of <file> holding <marker>
  local d; d="$(dirname "$1")"
  while :; do
    [[ -e "$d/$2" ]] && { echo "$d"; return 0; }
    [[ "$d" == "." || "$d" == "/" ]] && return 1
    d="$(dirname "$d")"
  done
}

while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  case "$f" in
    *.py)
      p="$(nearest "$f" pyproject.toml)" && command -v uv >/dev/null || continue
      uv run --quiet --project "$p" ruff format --quiet "$f" || true
      uv run --quiet --project "$p" ruff check --fix --quiet "$f" || true ;;
    *.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs|*.css|*.scss|*.html|*.vue|*.svelte)
      p="$(nearest "$f" node_modules/.bin/prettier)" || continue
      "$p/node_modules/.bin/prettier" --write --log-level silent "$f" || true ;;
    *.tf|*.tfvars)
      command -v terraform >/dev/null && terraform fmt "$f" >/dev/null || true ;;
  esac
done < <(git ls-files -m -o --exclude-standard)
exit 0
