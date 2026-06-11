#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Bash Commad to Nushell Command
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 🐚
# @raycast.description Convert clipboard bash multiline command to Nushell multiline command

set -euo pipefail

input="$(pbpaste)"

if [[ -z "$input" ]]; then
  echo "Clipboard is empty"
  exit 0
fi

converted="$(
  printf '%s\n' "$input" \
    | sed -E 's/[[:space:]]*\\[[:space:]]*$//' \
    | awk '
      BEGIN { print "(" }
      NF > 0 { print }
      END { print ")" }
    '
)"

printf '%s' "$converted" | pbcopy

echo "Copied converted command to clipboard:"
echo "$converted"
