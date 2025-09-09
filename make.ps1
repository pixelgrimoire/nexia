param(
    [string]$Target = 'help'
)

switch ($Target) {
    'bootstrap' { .\scripts\bootstrap.ps1 }
    'test'      { .\scripts\run_tests.ps1 }
    'check'     { & python scripts/check_duplicate_tests.py }
    'precommit-install' { python -m pip install --user pre-commit; pre-commit install }
    default     { & make $Target }
}
