#!/usr/bin/env bash
# Install the agent guardrails into the current repo, for one or more stacks.
#
#   bash <skill>/scripts/install-guardrails.sh python node terraform
#
# Never overwrites an existing file: it reports it instead, except `.gitignore`,
# which only receives the missing lines.
set -euo pipefail

ASSETS="$(cd "$(dirname "$0")/../assets" && pwd)"
STACKS=("$@")
[[ ${#STACKS[@]} -gt 0 ]] || { echo "Usage: install-guardrails.sh <python|node|terraform>..." >&2; exit 1; }
for s in "${STACKS[@]}"; do
  [[ -f "$ASSETS/precommit/$s.yaml" ]] || { echo "Unknown stack: $s (python, node, terraform)" >&2; exit 1; }
done

git rev-parse --show-toplevel >/dev/null 2>&1 || git init -q -b main
cd "$(git rev-parse --show-toplevel)"

added=(); kept=()
put() { # put <asset-relative-path> <destination>
  if [[ -e "$2" ]]; then kept+=("$2"); else mkdir -p "$(dirname "$2")"; cp "$ASSETS/$1" "$2"; added+=("$2"); fi
}

while IFS= read -r f; do
  rel="${f#"$ASSETS/common/"}"
  case "$rel" in gitignore|AGENTS.md) continue ;; esac
  put "common/$rel" "$rel"
done < <(find "$ASSETS/common" -type f)
chmod +x .agents/hooks/*.sh

touch .gitignore
while IFS= read -r line; do
  grep -qxF -- "$line" .gitignore || echo "$line" >> .gitignore
done < "$ASSETS/common/gitignore"

if [[ -e AGENTS.md ]]; then
  kept+=("AGENTS.md")
else
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "<!-- gates -->" ]]; then
      for s in "${STACKS[@]}"; do cat "$ASSETS/gates/$s.md"; done
    else
      printf '%s\n' "$line"
    fi
  done < "$ASSETS/common/AGENTS.md" > AGENTS.md
  added+=("AGENTS.md")
fi

if [[ -e .pre-commit-config.yaml ]]; then
  kept+=(".pre-commit-config.yaml")
else
  { echo "repos:"; cat "$ASSETS/precommit/common.yaml"; for s in "${STACKS[@]}"; do cat "$ASSETS/precommit/$s.yaml"; done; } > .pre-commit-config.yaml
  added+=(".pre-commit-config.yaml")
fi

if [[ " ${STACKS[*]} " == *" python "* && -f pyproject.toml ]] && ! grep -q '^\[tool.ruff' pyproject.toml; then
  cat "$ASSETS/ruff.toml.snippet" >> pyproject.toml
  added+=("pyproject.toml: [tool.ruff]")
fi

echo "Stacks: ${STACKS[*]}"
if [[ ${#added[@]} -gt 0 ]]; then echo "Added:"; printf '  %s\n' "${added[@]}"; fi
if [[ ${#kept[@]} -gt 0 ]]; then echo "Kept existing (merge by hand if needed):"; printf '  %s\n' "${kept[@]}"; fi
