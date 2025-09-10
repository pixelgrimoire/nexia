#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x .venv/bin/python ]; then
  echo "Creating virtualenv at .venv"
  python -m venv .venv
fi

. .venv/bin/activate
pip install -q -r requirements-dev.txt

alembic upgrade head
echo "Done"

