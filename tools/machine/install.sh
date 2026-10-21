#!/usr/bin/env bash
# Finish a fresh Work clone in one command: clone or create brain/, optionally brain-perso/, then run bootstrap.
# Run from a clone of this repository. Never modifies home-directory configuration, never commits or pushes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: tools/machine/install.sh [options]

  --brain <url>         Clone an existing private brain into brain/.
                        Without it, a blank brain is created from kit/brain/seed/
                        (fresh Git repository, no commit, no remote).
  --brain-perso <url|new>
                        Optional second brain in brain-perso/: clone <url>,
                        or create a blank one from kit/brain/seed/ with "new".
  --no-bootstrap        Stop after preparing the brains; do not run tools/machine/bootstrap.sh.
  -h, --help            Show this help.
EOF
}

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
command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }

# Clone <url> into <target>, create it blank with "new", or keep an existing clone.
prepare_brain() {
  local target="$1" source="$2"
  if [[ -d "$target/.git" ]]; then
    echo "$target/ already present; left as is."
  elif [[ -e "$target" ]]; then
    echo "$target/ exists but is not a Git repository; move it aside first." >&2
    exit 1
  elif [[ "$source" == "new" ]]; then
    uv run tools/brain/new-brain.py "$target"
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
  ./tools/machine/bootstrap.sh
else
  echo "Skipped bootstrap; run ./tools/machine/bootstrap.sh when ready."
fi

cat <<'EOF'

Next steps:
  - Fill in <brain>/.data/brain.json for each brain (scope, description, and the remote and
    user.email patterns that tools/machine/doctor.py checks against Git).
  - Fill in brain/me/about-me.md and review brain/AGENTS.md and brain/.data/local-paths.json.
  - Skills live in your brains: own skills in <brain>/skills/<name>/, third-party skills in
    <brain>/.data/work-config.json; machine-only choices (e.g. {"skills": {"disabled": [...]}}) in
    work-config.local.json. Then run tools/machine/update.sh.
  - Obsidian is not managed here: configure it by hand, see kit/obsidian/README.md.
  - Shared brain conventions live in kit/brain/ and follow Work updates (git pull starter main).
  - Give each new brain a private remote yourself, then commit and push when ready.
  - Check your Git identities: git config --show-origin --get-regexp '^(user|core\.sshcommand)'
EOF
