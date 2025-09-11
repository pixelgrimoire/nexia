Developer quick commands

Use the Makefile for common tasks on POSIX. On Windows PowerShell, use `make.ps1` which forwards to the same scripts.

POSIX (Linux/macOS):

```sh
make bootstrap   # create .venv and install deps
make test        # run duplicate-test checker and pytest
make check       # run duplicate-test checker only
make ci          # runs duplicate-test checker + pytest (CI-like)
make migrate     # apply Alembic migrations to DATABASE_URL
```
ci-local (POSIX, Docker required)
--------------------------------
Run the CI checks inside a transient Python container to avoid polluting your host environment:

```sh
make ci-local
```

This spins up a `python:3.12-slim` container, creates a `.venv` inside the project mount, installs the service requirements and runs the `ci` target.

Windows (Docker)
-----------------
If you have Docker Desktop on Windows you can run the same transient container using the PowerShell wrapper:

```powershell
.\make.ps1 ci-local
```

Troubleshooting
---------------
If Docker is installed but `ci-local` fails, ensure Docker Desktop is running and that Windows containers / WSL integration is enabled. See https://docs.docker.com/get-started/

Force WSL run
-------------
If you'd rather run the CI flow directly under WSL (skips Docker), use:

```powershell
.\make.ps1 ci-local-wsl
```

Windows (PowerShell):

```powershell
# bootstrap
.\make.ps1 bootstrap
# run tests
.\make.ps1 test
# run the CI-like checks
.\make.ps1 ci
```

These wrappers call the scripts in `./scripts/` so you can also run them directly.

Note: on Windows `.\make.ps1 ci` runs the duplicate-test checker and `pytest` using the repo `.venv` when available.

Pre-commit
----------
Install and enable pre-commit hooks locally to catch issues early:

POSIX:
```sh
pip install --user pre-commit
pre-commit install
```

Migrations
----------
The repo includes Alembic migrations targeting `packages.common.models.Base`.

POSIX:
```sh
./scripts/migrate.sh
```

Windows (PowerShell):
```powershell
./scripts/migrate.ps1
```

Ensure `DATABASE_URL` points to your Postgres instance (see `.env.example`). If not set, both migrate scripts try `localhost:5432` (Docker Compose port mapping) and use it automatically when reachable.

Windows (PowerShell):
```powershell
python -m pip install --user pre-commit
pre-commit install
```

