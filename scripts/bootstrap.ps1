param()

# Create virtualenv if missing
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$venv = Join-Path $repoRoot '.venv'
if (-not (Test-Path $venv)) {
    Write-Host "Creating virtualenv at $venv"
    python -m venv $venv
}

Write-Host "Upgrading pip and installing requirements"
try {
    & "$venv\Scripts\pip.exe" install --upgrade pip setuptools
    & "$venv\Scripts\pip.exe" install -r services/flow-engine/requirements.txt
    & "$venv\Scripts\pip.exe" install -r services/messaging-gateway/requirements.txt
    & "$venv\Scripts\pip.exe" install -r services/contacts/requirements.txt
    & "$venv\Scripts\pip.exe" install -r services/api-gateway/requirements.txt
    & "$venv\Scripts\pip.exe" install -r services/analytics/requirements.txt
    try { & "$venv\Scripts\pip.exe" install -r requirements-dev.txt } catch { Write-Host "No dev requirements" }
    try { & "$venv\Scripts\pip.exe" install -r services/webhook-receiver/requirements.txt } catch { Write-Host "No webhook-receiver requirements" }
} catch {
    Write-Host "pip install failed: $_"
}

Write-Host "Bootstrap complete"
