This project uses pytest for unit tests. A few conventions and quick commands to keep tests discoverable and avoid name collisions:

- Keep test module basenames unique across services. Prefer suffixing by service when a test name is generic, e.g. `test_trace_flow.py` or `test_logs_messaging.py`.
- Avoid top-level scripts that execute side effects at import time. Guard runners with `if __name__ == '__main__'`.
- Run tests locally using the project venv (if present) to match CI:

```powershell
# create venv (once)
python -m venv .venv
.\.venv\Scripts\pip.exe install -U pip
.\.venv\Scripts\pip.exe install -r services/flow-engine/requirements.txt
.\.venv\Scripts\pip.exe install -r services/messaging-gateway/requirements.txt

# run all tests
.\.venv\Scripts\python.exe -m pytest -q
```

- CI runs `pytest -q` at repo root. If you add tests, pick unique names or add a service-specific suffix.

Helper scripts
 - Windows (PowerShell):

```powershell
.\scripts\bootstrap.ps1   # creates .venv and installs service deps
.\scripts\run_tests.ps1  # runs duplicate checker and pytest using selected venv
```

 - POSIX (macOS / Linux):

```bash
./scripts/bootstrap.sh
./scripts/run_tests.sh
```

If you want, I can open a PR that consolidates the remaining test files and updates the workflow with a small lint step to detect duplicate basenames.

Pre-commit (optional but recommended)

Windows (PowerShell):

```powershell
# install into repo venv (recommended)
python -m pip install --upgrade pip
pip install pre-commit
pre-commit install
```

POSIX/macOS:

```bash
python -m pip install --upgrade pip
pip install pre-commit
pre-commit install
```

Once installed, the duplicate-test check runs automatically on commit; CI also runs the same check.
