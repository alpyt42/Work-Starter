#!/bin/zsh
# Build a local AppleScript .app for the task manager. No Dock changes here.
set -euo pipefail

script_dir=${0:A:h}
work_dir=${script_dir:h:h}
output_dir="$work_dir/artifacts/internal/setup/tasks-dock-app"
app_path="$output_dir/Actions Brain.app"
launcher="$script_dir/launcher.sh"

if [[ ! -f "$launcher" || ! -f "$script_dir/tasks-web.py" ]]; then
  print -u2 'The launcher or the tasks server was not found.'
  exit 1
fi
if [[ "$launcher" == *'"'* || "$launcher" == *'\\'* ]]; then
  print -u2 "The launcher path contains an unsupported character."
  exit 1
fi

/bin/mkdir -p "$output_dir"
script_path="$output_dir/launch.applescript"
cat > "$script_path" <<APPLESCRIPT
on run
    try
        do shell script ("/bin/zsh " & quoted form of "$launcher")
    on error errorMessage
        display dialog ("Could not open Actions. " & errorMessage) buttons {"OK"} default button "OK" with icon stop
    end try
end run
APPLESCRIPT

/usr/bin/osacompile -o "$app_path" "$script_path"
/usr/bin/plutil -replace CFBundleIdentifier -string 'local.work.tasks-brain' "$app_path/Contents/Info.plist"
cat > "$output_dir/README.md" <<'README'
# Actions Brain app

Local app generated with `tools/tasks-web/build-dock-app.sh` from the Work repository. It runs `tools/tasks-web/launcher.sh`, which starts the tasks server if needed and opens the local page in the default browser. The code and the data stay in Work; this app is a local deliverable that is not versioned.

To rebuild it, move or delete this generated app, then run the build command again from Work. The **Quit** button in the page stops the local server. Restarting the Mac stops it too.
README

print -r -- "$app_path"
