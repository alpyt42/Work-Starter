#!/usr/bin/env bash
# Agent hook (PreToolUse, Claude Code and Codex): block, before it runs, any
# command or file read that touches a secret, and any destructive git command.
# `.env.example` stays allowed. Exit 2 blocks the call and shows the reason.
input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command? // "" | strings' 2>/dev/null)"
target="$(printf '%s' "$input" | jq -r '[.tool_input.command?, .tool_input.file_path?, .tool_input.path?, .tool_input.pattern?] | map(strings) | join(" ")' 2>/dev/null)"
[[ -z "$target" ]] && exit 0

block() { echo "Blocked by .agents/hooks/guard.sh: $1" >&2; exit 2; }

t="${target//.env.example/}"
end='([[:space:]"'"'"'=<>|;&()`]|$)'
start='(^|[/[:space:]"'"'"'=<>|;&(`])'
if printf '%s' "$t" | grep -Eq "${start}\.env([.][A-Za-z0-9_-]+)?${end}" \
  || printf '%s' "$t" | grep -Eq "\.(pem|key|p12|pfx|tfstate)${end}" \
  || printf '%s' "$t" | grep -Eq "(\.ssh|\.aws|\.gnupg)(/|${end})|id_(rsa|ed25519|ecdsa)" \
  || printf '%s' "$t" | grep -Eq "(^|[;&|[:space:]])(printenv|env)[[:space:]]*($|[|;&])"; then
  block "this touches a secret (.env, key, ~/.ssh, ~/.aws, env dump). Use .env.example for variable names; ask the user if a value is really needed."
fi

git='(^|[;&|[:space:](])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+'
if printf '%s' "$cmd" | grep -Eq "${git}(push|reset[[:space:]]+--hard|clean[[:space:]]+-[a-zA-Z]*f|branch[[:space:]]+-D|checkout[[:space:]]+(--[[:space:]]+)?\.([[:space:]]|$)|restore[[:space:]]+\.([[:space:]]|$))" \
  || printf '%s' "$cmd" | grep -Eq -- "--no-verify"; then
  block "destructive or remote git command (push, reset --hard, clean -f, branch -D, checkout/restore ., --no-verify). Ask the user to run it."
fi
exit 0
