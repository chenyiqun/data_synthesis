#!/usr/bin/env bash
set -euo pipefail

BRANCH="${GIT_BRANCH:-main}"
REMOTE="${GIT_REMOTE:-origin}"
REPO_URL="${REPO_URL:-https://github.com/chenyiqun/data_synthesis.git}"

cd "$(dirname "$0")"

if [ ! -d ".git" ]; then
  echo "Error: this directory is not a cloned git repository."
  echo "Clone first:"
  echo "  git clone $REPO_URL"
  echo "  cd data_synthesis"
  exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  git remote add "$REMOTE" "$REPO_URL"
fi

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "Error: local changes exist on the server. Commit, stash, or remove them before syncing."
  git status --short
  exit 1
fi

git fetch "$REMOTE" "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH"

echo "Synced latest code from $REMOTE/$BRANCH successfully."
