#!/usr/bin/env bash
set -euo pipefail

BRANCH="${GIT_BRANCH:-main}"
REMOTE="${GIT_REMOTE:-origin}"
REPO_URL="${REPO_URL:-https://github.com/chenyiqun/data_synthesis.git}"

echo "[INFO] repo url: $REPO_URL"
echo "[INFO] branch  : $BRANCH"
echo "[INFO] cwd     : $(pwd)"

if [ ! -d ".git" ]; then
  echo "[ERROR] Current directory is not a git repository."
  echo "If you want to clone first, run this from the parent directory:"
  echo "  cd .."
  echo "  git clone --branch $BRANCH $REPO_URL data_synthesis"
  exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  git remote add "$REMOTE" "$REPO_URL"
fi

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "[ERROR] Local changes exist. Commit, stash, or remove them before syncing."
  git status --short
  exit 1
fi

echo "[INFO] Fetching latest code..."
git fetch "$REMOTE" "$BRANCH"

echo "[INFO] Checking out branch..."
git checkout "$BRANCH"

echo "[INFO] Pulling latest code..."
git pull --ff-only "$REMOTE" "$BRANCH"

echo "[INFO] Synced latest code from $REMOTE/$BRANCH successfully."