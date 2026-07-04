#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Bash Command to Nushell Command
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 🐚
# @raycast.description Convert clipboard Bash command to Nushell command

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
input="$(pbpaste)"

if [[ -z "$input" ]]; then
  echo "Clipboard is empty"
  exit 0
fi

if ! converted="$(printf '%s' "$input" | python3 "$script_dir/scripts/bash_to_nushell.py" 2>&1)"; then
  echo "$converted"
  exit 1
fi

printf '%s' "$converted" | pbcopy

echo "Copied converted command to clipboard:"
echo "$converted"
