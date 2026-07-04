#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title GitHub Image Auto Resizer
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 🖼️
# @raycast.description Convert GitHub user-attachments URLs in clipboard to resized img tags

set -euo pipefail

input_text="$(pbpaste || true)"

if [[ -z "${input_text//[[:space:]]/}" ]]; then
  echo "Clipboard is empty"
  exit 0
fi

urls="$(
  printf '%s\n' "$input_text" \
    | grep -oE 'https://github\.com/user-attachments/assets/[^)[:space:]]+' \
    || true
)"

img_count="$(printf '%s\n' "$urls" | grep -c '.' || true)"

if [[ "$img_count" -eq 0 ]]; then
  echo "No GitHub images found in clipboard"
  exit 1
fi

if [[ "$img_count" -le 2 ]]; then
  width="49%"
else
  width="32%"
fi

replaced_text=""
while IFS= read -r url; do
  if [[ -n "$url" ]]; then
    replaced_text+="<img src=\"$url\" width=\"$width\"> "
  fi
done <<< "$urls"

printf '%s' "${replaced_text% }" | pbcopy

echo "Resized $img_count GitHub image(s) to $width!"
