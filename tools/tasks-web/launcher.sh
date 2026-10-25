#!/bin/zsh
# Start the local task manager on demand, then open it in the default browser.
set -euo pipefail

script_dir=${0:A:h}
work_dir=${script_dir:h:h}
url='http://127.0.0.1:8765/'
api_url="${url}api/actions"

ready() {
  local response
  response=$(/usr/bin/curl --silent --show-error --fail --noproxy '*' --max-time 2 "$api_url" 2>/dev/null) || return 1
  [[ "$response" == *'"actions"'* && "$response" == *'"registers"'* ]]
}

if ready; then
  /usr/bin/open "$url"
  exit 0
fi

# If something else owns the port, do not open it or launch a second server.
if /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  for attempt in {1..25}; do
    if ready; then
      /usr/bin/open "$url"
      exit 0
    fi
    /bin/sleep 0.2
  done
  print -u2 'Port 8765 is already used by another application. Close it before starting Actions.'
  exit 1
fi

export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH}"
uv_bin=$(command -v uv || true)
if [[ -z "$uv_bin" ]]; then
  print -u2 'uv was not found. Install or restore uv, then start Actions again.'
  exit 1
fi

/bin/mkdir -p "$work_dir/agents"
log_file="$work_dir/agents/tasks-web.log"
cd "$work_dir"
/usr/bin/nohup "$uv_bin" run "$script_dir/tasks-web.py" --port 8765 >"$log_file" 2>&1 </dev/null &
server_pid=$!
print -r -- "$server_pid" > "$work_dir/agents/tasks-web.pid"

for attempt in {1..50}; do
  if ready; then
    /usr/bin/open "$url"
    exit 0
  fi
  /bin/sleep 0.2
done

print -u2 "Actions did not start. See agents/tasks-web.log in Work."
exit 1
