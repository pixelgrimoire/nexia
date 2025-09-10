param(
    [string]$Target = 'help'
)

switch ($Target) {
    'help' {
        Write-Host "Available targets:";
        Write-Host "  bootstrap                 - create .venv and install service deps (POSIX)";
        Write-Host "  test                      - run duplicate test checker and pytest (POSIX)";
        Write-Host "  check                     - run duplicate test checker";
        Write-Host "  precommit-install         - install pre-commit locally";
        Write-Host "  precommit-install-venv    - create .venv and install pre-commit into it, then enable hooks";
        Write-Host "  ci                        - run duplicate test checker and pytest using repo venv";
        Write-Host "  ci-local                  - run CI checks inside Docker (POSIX)";
        Write-Host "  ci-local-wsl              - run CI checks inside WSL (Windows)";
        exit 0
    }
    'bootstrap' { .\scripts\bootstrap.ps1 }
    'test'      { .\scripts\run_tests.ps1 }
    'check'     { & python scripts/check_duplicate_tests.py }
    'ci'        {
        # prefer repo .venv python on Windows
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $venvPy = Join-Path $scriptDir '.venv\Scripts\python.exe'
        if (Test-Path $venvPy) {
            Write-Host "Using venv python: $venvPy"
            & $venvPy scripts/check_duplicate_tests.py
            & $venvPy -m pytest -q
        } else {
            $sysPy = (Get-Command python).Source
            Write-Host "Using system python: $sysPy"
            & python scripts/check_duplicate_tests.py
            & python -m pytest -q
        }
    }
    'precommit-install' { python -m pip install --user pre-commit; pre-commit install }
    'precommit-install-venv' {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $venvActivate = Join-Path $scriptDir '.venv\Scripts\Activate.ps1'
        if (-Not (Test-Path $venvActivate)) {
            Write-Host "Creating .venv at $scriptDir\.venv"
            python -m venv "$scriptDir\.venv"
        }
        Write-Host "Activating venv and installing pre-commit"
        . $venvActivate
        python -m pip install --upgrade pip
        pip install pre-commit
        pre-commit install
    }
    'ci-local' {
        # Run CI checks inside a transient python container using Docker (Windows)
        $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
        $dockerOk = $false
        if ($dockerCmd) {
            try {
                & docker info > $null 2>&1
                $dockerOk = $true
            } catch {
                $dockerOk = $false
            }
        }

        $pwd = (Get-Location).Path
        $bind = "$($pwd):/work"

        # Prefer WSL when available to avoid Docker Desktop issues
        $wslCmd = Get-Command wsl -ErrorAction SilentlyContinue
        if ($wslCmd) {
            try {
                $wslPath = & wsl wslpath -a -u "$pwd" 2>$null
                $wslPath = $wslPath.Trim()
            } catch {
                $wslPath = ""
            }
            if (-not [string]::IsNullOrEmpty($wslPath)) {
                Write-Host "Running CI inside WSL at $wslPath"
                & wsl bash -lc "cd '$wslPath' && python -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && pip install -r services/flow-engine/requirements.txt || true && pip install -r services/messaging-gateway/requirements.txt || true && pip install pre-commit pytest && make ci"
                exit 0
            }
        }

        if ($dockerOk) {
            Write-Host "Starting docker container to run CI checks (mount: $bind)"
            & docker run --rm -v $bind -w /work python:3.12-slim bash -lc "set -e; python -m venv .venv; . .venv/bin/activate; python -m pip install --upgrade pip; pip install -r services/flow-engine/requirements.txt || true; pip install -r services/messaging-gateway/requirements.txt || true; pip install pre-commit pytest; make ci"
            exit 0
        }

        Write-Host "Neither WSL nor Docker are available/usable. Install Docker Desktop or enable WSL and try again." -ForegroundColor Red
        exit 1
    }
    'ci-local-wsl' {
        # Force running CI inside WSL (Windows)
        $wslCmd = Get-Command wsl -ErrorAction SilentlyContinue
        if (-not $wslCmd) {
            Write-Host "WSL not found. Enable WSL or install WSL/WSL2 and try again." -ForegroundColor Red
            exit 1
        }
        $pwd = (Get-Location).Path
        try {
            $wslPath = & wsl wslpath -a -u "$pwd" 2>$null
            $wslPath = $wslPath.Trim()
        } catch {
            $wslPath = ""
        }

        if (-not [string]::IsNullOrEmpty($wslPath)) {
            Write-Host "Running CI inside WSL at $wslPath"
            & wsl bash -lc "cd '$wslPath' && python -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && pip install -r services/flow-engine/requirements.txt || true && pip install -r services/messaging-gateway/requirements.txt || true && pip install pre-commit pytest && make ci"
            exit 0
        }

        # Fallback: construct a WSL-style path from the Windows path: C:\path -> /mnt/c/path
        if ($pwd -match '^[A-Za-z]:\\') {
            $drive = $pwd.Substring(0,1).ToLower()
            $rest = $pwd.Substring(2) # skip 'C:'
            $rest = $rest -replace '\\','/'
            if ($rest.StartsWith('/')) { $rest = $rest.Substring(1) }
            $fallback = "/mnt/$drive/$rest"
            Write-Host "Attempting WSL path fallback: $fallback"
            & wsl bash -lc "cd '$fallback' && python -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && pip install -r services/flow-engine/requirements.txt || true && pip install -r services/messaging-gateway/requirements.txt || true && pip install pre-commit pytest && make ci"
            if ($LASTEXITCODE -eq 0) { exit 0 }
        }

        Write-Host "Could not determine WSL path for the repo. Please run the CI checks manually inside WSL." -ForegroundColor Red
        exit 1
    }
    default     { & make $Target }
}
