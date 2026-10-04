# Local Django + temporary public HTTPS URL in ONE terminal window.
# Usage: from stegastiko/, run: .\scripts\start-local-and-public.ps1

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Host.UI.RawUI.WindowTitle = "Stegastiko - public URL appears here"

function Stop-ListenersOnPort8000 {
    Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Seconds 1
}

function Start-DjangoProcess {
    Stop-ListenersOnPort8000
    return Start-Process -FilePath "python" `
        -ArgumentList @("manage.py", "runserver", "127.0.0.1:8000") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru
}

function Stop-DjangoProcess {
    param($Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

$script:django = $null

Write-Host "Waiting for public tunnel URL before starting Django..." -ForegroundColor Yellow
Write-Host "Watch THIS window for the green PUBLIC URL banner." -ForegroundColor Yellow
Write-Host ""

Set-Location $ProjectRoot

try {
    & "$PSScriptRoot\start-remote-demo.ps1" -OnPublicUrlReady {
        Write-Host "Starting Django with updated .env..." -ForegroundColor Yellow
        Stop-DjangoProcess -Process $script:django
        $script:django = Start-DjangoProcess
        Start-Sleep -Seconds 2
        Write-Host "Django ready at http://127.0.0.1:8000/" -ForegroundColor Green
    }
} finally {
    Stop-DjangoProcess -Process $script:django
    Stop-ListenersOnPort8000
}
