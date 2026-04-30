#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Prepend Obsidian Tasks
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 🤖
# @raycast.packageName Obsidian
# @raycast.argument1 { "type": "text", "placeholder": "Task" }

set -euo pipefail

FILE="$HOME/Documents/Obsidian Vault/Tasks.md"
TASK="${1:-}"
TODAY="$(date +%F)"

if [[ -z "${TASK//[[:space:]]/}" ]]; then
  echo "Task is empty"
  exit 1
fi

if [[ ! -f "$FILE" ]]; then
  echo "File not found: $FILE"
  exit 1
fi

ed -s "$FILE" <<EOF
0a
- [ ] $TASK ➕ $TODAY 🛫 $TODAY
.
w
q
EOF

echo "Added: $TASK"
