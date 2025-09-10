#!/usr/bin/env bash
set -euo pipefail
repoRoot="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repoRoot"
if [ ! -d ".venv" ]; then
  python -m venv .venv
fi
.venv/bin/pip install --upgrade pip setuptools
.venv/bin/pip install -r services/flow-engine/requirements.txt
.venv/bin/pip install -r services/messaging-gateway/requirements.txt
.venv/bin/pip install -r services/contacts/requirements.txt
echo "Bootstrap complete"
