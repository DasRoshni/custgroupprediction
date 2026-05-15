#!/usr/bin/env bash
# Install the Google Cloud SDK on macOS via Homebrew.
# Idempotent: no-op if gcloud is already on PATH.
set -euo pipefail

if command -v gcloud >/dev/null 2>&1; then
  echo "gcloud already installed: $(gcloud --version | head -1)"
  exit 0
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "ERROR: Homebrew not found. Install from https://brew.sh and re-run." >&2
  exit 1
fi

echo "==> Installing google-cloud-sdk via Homebrew (~2 minutes)"
brew install --cask google-cloud-sdk

cat <<EOF

==> Done. To use gcloud in the current shell:

    source "\$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
    source "\$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"

Or open a new terminal. Then run: make gcp-bootstrap PROJECT_ID=<your-project>
EOF
