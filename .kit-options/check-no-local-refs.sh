#!/usr/bin/env bash
# check-no-local-refs.sh — un repo partagé ne doit contenir aucune référence au monde local.
# À copier dans `tools/` du repo partagé (et à citer dans son AGENTS.md), ou à lancer à la main avant un push.
# Usage : tools/check-no-local-refs.sh [chemin]   (défaut : la racine du repo)
set -euo pipefail
root="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PATTERNS='/Users/[a-z]|/home/[a-z]+/|~/Work|~/work|\bbrain/|\brepos/[a-z-]+/|voir ma note|see my note'
if git -C "$root" grep -nIE "$PATTERNS" -- . ':!tools/check-no-local-refs.sh' 2>/dev/null; then
  echo "✗ références au monde local trouvées — porte l'info dans le repo, cite les autres repos par URL" >&2
  exit 1
fi
echo "✓ aucune référence locale"
