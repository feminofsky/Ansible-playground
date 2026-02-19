#!/bin/bash
# Run after creating the argocd repo on GitHub.
# Usage: ./scripts/setup-argocd-submodule.sh [repo-url]
# Default: git@github.com:feminofsky/ansible-argocd.git

set -e
REPO_URL="${1:-git@github.com:feminofsky/ansible-argocd.git}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Pushing argocd to $REPO_URL ..."
(cd argocd && \
  (git remote remove origin 2>/dev/null || true) && \
  git remote add origin "$REPO_URL" && \
  git fetch origin && \
  git pull origin main --allow-unrelated-histories --no-edit 2>/dev/null || true && \
  git push -u origin main)

echo "Converting to submodule ..."
git rm -r --cached argocd 2>/dev/null || true
git submodule add "$REPO_URL" argocd

echo "Done. Commit and push:"
echo "  git add .gitmodules argocd"
echo "  git commit -m 'Convert argocd to git submodule'"
echo "  git push"
