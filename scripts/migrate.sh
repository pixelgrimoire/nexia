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

# If DATABASE_URL is not set, prefer localhost:5432 (Compose port mapping)
if [ -z "${DATABASE_URL:-}" ]; then
  if echo >/dev/tcp/localhost/5432 2>/dev/null; then
    export DATABASE_URL="postgresql+psycopg://nf_user:nf_pass@localhost:5432/nexia"
    echo "DATABASE_URL not set; using localhost:5432 (Compose port)"
  else
    echo "DATABASE_URL not set and localhost:5432 not reachable; falling back to default in Alembic env (host 'postgres')."
  fi
fi

alembic upgrade head
echo "Done"
