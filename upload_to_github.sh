#!/usr/bin/env bash
set -euo pipefail

BRANCH="${GIT_BRANCH:-main}"
REMOTE="${GIT_REMOTE:-origin}"
COMMIT_MESSAGE="${1:-Update data_synthesis}"

cd "$(dirname "$0")"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: current directory is not a git repository."
  exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "Error: git remote '$REMOTE' does not exist."
  echo "Run: git remote add $REMOTE https://github.com/chenyiqun/data_synthesis.git"
  exit 1
fi

git fetch "$REMOTE" "$BRANCH"
git checkout "$BRANCH"

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git add -A
  git commit -m "$COMMIT_MESSAGE"
else
  echo "No local changes to commit."
fi

git pull --rebase "$REMOTE" "$BRANCH"
git push "$REMOTE" "$BRANCH"

echo "Uploaded to $REMOTE/$BRANCH successfully."
