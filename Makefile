SHELL := /bin/bash

.PHONY: help bootstrap test check precommit-install ci

help:
	@echo "Available targets:"
	@echo "  make bootstrap         - create .venv and install service deps (POSIX)"
	@echo "  make test              - run duplicate test checker and pytest (POSIX)"
	@echo "  make check             - run duplicate test checker"
	@echo "  make precommit-install - install pre-commit locally"

bootstrap:
	./scripts/bootstrap.sh

test:
	./scripts/run_tests.sh

check:
	python scripts/check_duplicate_tests.py

precommit-install:
	pip install --user pre-commit
	pre-commit install
# Makefile de ejemplo

ci:
	python scripts/check_duplicate_tests.py
	pytest -q
