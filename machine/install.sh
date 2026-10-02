#!/usr/bin/env bash
# Finish a fresh Work clone in one command: clone or create brain/, optionally brain-perso/, then run bootstrap.
# Run from a clone of this repository. Never modifies home-directory configuration, never commits or pushes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: machine/install.sh [options]

  --brain <url>         Clone an existing private brain into brain/.
                        Without it, a blank brain is created from brain-starter
                        (fresh history, no remote).
  --brain-perso <url|new>
                        Optional second brain in brain-perso/: clone <url>,
                        or create a blank one from brain-starter with "new".
  --no-bootstrap        Stop after preparing the brains; do not run machine/bootstrap.sh.
  -h, --help            Show this help.

BRAIN_STARTER_URL overrides the brain-starter source.
EOF
}

BRAIN_STARTER_URL="${BRAIN_STARTER_URL:-https://github.com/alpyt42/brain-starter.git}"
BRAIN_URL=""
BRAIN_PERSO=""
BOOTSTRAP=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --brain) BRAIN_URL="${2:?--brain needs a URL}"; shift 2 ;;
    --brain-perso) BRAIN_PERSO="${2:?--brain-perso needs a URL or new}"; shift 2 ;;
    --no-bootstrap) BOOTSTRAP=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }

# A blank brain: brain-starter's files with a fresh history and no remote.
new_brain() {
  local target="$1"
  git clone --quiet --depth 1 "$BRAIN_STARTER_URL" "$target"
  rm -rf "$target/.git"
  git -C "$target" init --quiet -b main
  echo "Created blank $target/ from brain-starter (no commit, no remote)."
}

# Clone <url> into <target>, create it blank with "new", or keep an existing clone.
prepare_brain() {
  local target="$1" source="$2"
  if [[ -d "$target/.git" ]]; then
    echo "$target/ already present; left as is."
  elif [[ -e "$target" ]]; then
    echo "$target/ exists but is not a Git repository; move it aside first." >&2
    exit 1
  elif [[ "$source" == "new" ]]; then
    new_brain "$target"
  else
    git clone "$source" "$target"
  fi
}

# 1. Leave origin free for the user's own Work repository.
origin="$(git remote get-url origin 2>/dev/null || true)"
if [[ "$origin" == *Work-Starter* ]] && ! git remote get-url starter >/dev/null 2>&1; then
  git remote rename origin starter
  echo "Remote 'origin' (Work-Starter) renamed 'starter'. Add your own with: git remote add origin <url>"
fi

# 2. brain/ and optional brain-perso/
prepare_brain brain "${BRAIN_URL:-new}"
[[ -z "$BRAIN_PERSO" ]] || prepare_brain brain-perso "$BRAIN_PERSO"

# 3. Skills, links and checks
if [[ "$BOOTSTRAP" == 1 ]]; then
  ./machine/bootstrap.sh
else
  echo "Skipped bootstrap; run ./machine/bootstrap.sh when ready."
fi

cat <<'EOF'

Next steps:
  - Fill in brain/about-me.md and declare your axes in brain/AGENTS.md ("Axes actifs").
  - Give each new brain a private remote yourself, then commit and push when ready.
  - Check your Git identities: git config --show-origin --get-regexp '^(user|core\.sshcommand)'
EOF
