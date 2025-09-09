Developer quick commands

Use the Makefile for common tasks on POSIX. On Windows PowerShell, use `make.ps1` which forwards to the same scripts.

POSIX (Linux/macOS):

```sh
make bootstrap   # create .venv and install deps
make test        # run duplicate-test checker and pytest
make check       # run duplicate-test checker only
make ci          # runs duplicate-test checker + pytest (CI-like)
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
