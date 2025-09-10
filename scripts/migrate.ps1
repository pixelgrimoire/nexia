param()

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$venvPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
$venvPip = Join-Path $repoRoot '.venv\Scripts\pip.exe'
$alembic = Join-Path $repoRoot '.venv\Scripts\alembic.exe'

if (-not (Test-Path $venvPy)) {
    Write-Host "Creating virtualenv at .venv"
    python -m venv .venv
}

Write-Host "Installing dev requirements (alembic)"
& $venvPip install -q -r requirements-dev.txt

Write-Host "Running alembic upgrade head"
& $alembic upgrade head

Write-Host "Done"

