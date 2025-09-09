param()

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
# prefer service-level venv if present
$repoVenv = Join-Path $repoRoot '.venv'
$flowVenv = Join-Path $repoRoot 'services\flow-engine\.venv'
$python = "python"
if (Test-Path "$flowVenv\Scripts\python.exe") { $python = "$flowVenv\Scripts\python.exe" }
elseif (Test-Path "$repoVenv\Scripts\python.exe") { $python = "$repoVenv\Scripts\python.exe" }

Write-Host "Running duplicate test checker"
& $python scripts/check_duplicate_tests.py

Write-Host "Running pytest"
& $python -m pytest -q
