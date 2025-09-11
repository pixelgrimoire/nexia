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

# If DATABASE_URL is not set, try localhost (Compose port mapping) before falling back
if (-not $env:DATABASE_URL) {
    $ok = $false
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', 5432, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(500)) {
            $client.EndConnect($iar)
            $ok = $true
        }
    } catch { $ok = $false } finally { if ($client) { $client.Close() } }
    if ($ok) {
        $env:DATABASE_URL = 'postgresql+psycopg://nf_user:nf_pass@localhost:5432/nexia'
        Write-Host "DATABASE_URL not set; using localhost:5432 (Compose port)"
    } else {
        Write-Host "DATABASE_URL not set and localhost:5432 not reachable; falling back to default in Alembic env (host 'postgres')."
    }
}

Write-Host "Running alembic upgrade head"
& $alembic upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Host "Alembic failed locally (exit code $LASTEXITCODE). Retrying inside Docker network..." -ForegroundColor Yellow
    $pwd = (Get-Location).Path
    $projName = Split-Path $repoRoot -Leaf
    $networkName = "${projName}_default"
    $cmd = "set -e; python -m pip install --upgrade pip; pip install -q -r requirements-dev.txt; alembic upgrade head"
    try {
        docker run --rm -v "${pwd}:/work" -w /work --network $networkName python:3.12-slim bash -lc $cmd
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Done (via Docker)"
            exit 0
        }
    } catch {
        Write-Host "Fallback via Docker failed. See errors above." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Done"
