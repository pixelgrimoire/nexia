#!/usr/bin/env bash
set -euo pipefail
repoRoot="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repoRoot"
python scripts/check_duplicate_tests.py
.venv/bin/python -m pytest -q
