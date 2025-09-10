SHELL := /bin/bash

.PHONY: help bootstrap test check precommit-install precommit-install-venv ci ci-local

help:
	@echo "Available targets:"
	@echo "  make bootstrap         - create .venv and install service deps (POSIX)"
	@echo "  make test              - run duplicate test checker and pytest (POSIX)"
	@echo "  make check             - run duplicate test checker"
	@echo "  make precommit-install - install pre-commit locally"
	@echo "  make precommit-install-venv - create .venv and install pre-commit into it, then enable hooks"
	@echo "  make ci-local           - run the CI checks inside a transient python:3.12 Docker container (POSIX)"

bootstrap:
	./scripts/bootstrap.sh

test:
	./scripts/run_tests.sh

check:
	python scripts/check_duplicate_tests.py

precommit-install:
	pip install --user pre-commit
	pre-commit install

precommit-install-venv:
	python -m venv .venv
	. .venv/bin/activate; python -m pip install --upgrade pip; pip install pre-commit
	. .venv/bin/activate; pre-commit install
# Makefile de ejemplo

ci:
	python scripts/check_duplicate_tests.py
	pytest -q

ci-local:
	@echo "Running CI checks inside python:3.12-slim container (requires Docker)"
	docker run --rm -v "$(PWD)":/work -w /work python:3.12-slim bash -lc "set -e; python -m venv .venv; . .venv/bin/activate; python -m pip install --upgrade pip; pip install -r services/flow-engine/requirements.txt; pip install -r services/messaging-gateway/requirements.txt; pip install pre-commit pytest; make ci"
