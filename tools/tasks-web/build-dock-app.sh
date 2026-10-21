#!/bin/zsh
# Build a local AppleScript .app for the task manager. No Dock changes here.
set -euo pipefail

script_dir=${0:A:h}
work_dir=${script_dir:h:h}
output_dir="$work_dir/artifacts/internal/setup/tasks-dock-app"
app_path="$output_dir/Actions Brain.app"
launcher="$script_dir/launcher.sh"

if [[ ! -f "$launcher" || ! -f "$script_dir/tasks-web.py" ]]; then
  print -u2 'Le lanceur ou le serveur de tâches est introuvable.'
  exit 1
fi
if [[ "$launcher" == *'"'* || "$launcher" == *'\\'* ]]; then
  print -u2 "Le chemin du lanceur contient un caractère non pris en charge."
  exit 1
fi

/bin/mkdir -p "$output_dir"
script_path="$output_dir/launch.applescript"
cat > "$script_path" <<APPLESCRIPT
on run
    try
        do shell script ("/bin/zsh " & quoted form of "$launcher")
    on error errorMessage
        display dialog ("Impossible d'ouvrir Actions. " & errorMessage) buttons {"OK"} default button "OK" with icon stop
    end try
end run
APPLESCRIPT

/usr/bin/osacompile -o "$app_path" "$script_path"
/usr/bin/plutil -replace CFBundleIdentifier -string 'local.work.tasks-brain' "$app_path/Contents/Info.plist"
cat > "$output_dir/README.md" <<'README'
# Application Actions Brain

Application locale générée avec `tools/tasks-web/build-dock-app.sh` depuis le dépôt Work. Elle lance `tools/tasks-web/launcher.sh`, qui démarre le serveur de tâches si besoin et ouvre la page locale dans le navigateur par défaut. Le code et les données restent dans Work ; cette app est un livrable local non versionné.

Pour la reconstruire, déplacer ou supprimer cette app générée puis relancer la commande de construction depuis Work. Le bouton **Quitter** dans la page arrête le serveur local. Un redémarrage du Mac l'arrête aussi.
README

print -r -- "$app_path"
