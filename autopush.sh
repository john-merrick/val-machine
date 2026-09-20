#!/bin/bash
# Watches for changes and auto-pushes to the dev branch.
# Usage: ./autopush.sh

BRANCH="dev"
INTERVAL=5  # seconds between checks

# Ensure we're on the dev branch
git checkout -B "$BRANCH" 2>/dev/null
git push -u origin "$BRANCH" 2>/dev/null

echo "Watching for changes... (Ctrl+C to stop)"

while true; do
  if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    echo "Changes detected — committing and pushing..."
    git add -A
    git commit -m "auto: $(date '+%Y-%m-%d %H:%M:%S')"
    git push origin "$BRANCH"
  fi
  sleep "$INTERVAL"
done
