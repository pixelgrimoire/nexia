Developer scripts

This folder contains convenience scripts and a small E2E smoke test used during development.

Run the E2E smoke test (posts a webhook into the webhook-receiver container and checks Redis):

```powershell
# from repo root
python scripts/e2e_test.py
```

Run the PowerShell E2E test (if you prefer PowerShell version):

```powershell
# from repo root
.\scripts\e2e_test.ps1
```

Run the small pure-Python unit-test runners (no venv required; these use shims to avoid installing deps):

```powershell
python services/flow-engine/tests/run_tests.py
python services/messaging-gateway/tests/run_tests.py
```

Run pytest in an isolated venv (recommended for accurate results):

```powershell
# create a venv at repo root
python -m venv .venv_test
& .\.venv_test\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r services/flow-engine/requirements.txt
pip install -r services/messaging-gateway/requirements.txt
# run pytest for flow-engine
pytest -q services/flow-engine/tests
# run pytest for messaging-gateway
pytest -q services/messaging-gateway/tests
# deactivate and remove venv when done
deactivate
Remove-Item -Recurse -Force .venv_test
```

Notes

- The E2E test posts into the `webhook-receiver` container using an in-container Python command so signature computation is correct.
- CI already runs the Python E2E smoke test and the flow-engine unit tests.
- If you see failures related to missing packages, create and activate a venv and install the requirements as shown above.
