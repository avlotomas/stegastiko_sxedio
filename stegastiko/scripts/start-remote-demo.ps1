# Temporary public HTTPS URL via localhost.run (new hostname each session).
# Usage: from stegastiko/, run: .\scripts\start-remote-demo.ps1
# Keep Django running: python manage.py runserver 127.0.0.1:8000

param(
    [scriptblock]$OnPublicUrlReady
)

# ssh writes banners to stderr; must not use Stop or the script exits immediately.
$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

$EnvPath = Join-Path $ProjectRoot ".env"
$ExampleEnvPath = Join-Path $ProjectRoot ".env.example"

function Write-EnvFileUtf8NoBom {
    param([string[]]$Lines)

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($EnvPath, $Lines, $utf8NoBom)
}

function Ensure-EnvFile {
    if (-not (Test-Path $EnvPath)) {
        if (Test-Path $ExampleEnvPath) {
            Copy-Item $ExampleEnvPath $EnvPath
        } else {
            throw "Missing .env and .env.example in $ProjectRoot"
        }
    }
}

function Show-PublicUrl {
    param([string]$TunnelHost)

    $origin = "https://$TunnelHost"
    $login = "$origin/login/"
    $bar = "============================================================"

    Write-Host ""
    Write-Host $bar -ForegroundColor Green
    Write-Host " PUBLIC URL (share with external users)" -ForegroundColor Green
    Write-Host $bar -ForegroundColor Green
    Write-Host ""
    Write-Host "  $origin/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Login: $login" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Local:  http://127.0.0.1:8000/" -ForegroundColor DarkGray
    Write-Host $bar -ForegroundColor Green
    Write-Host ""
}

function Set-DjangoTunnelHost {
    param([string]$TunnelHost)

    Ensure-EnvFile
    $origin = "https://$TunnelHost"
    $allowed = "127.0.0.1,localhost,$TunnelHost"
    $lines = Get-Content $EnvPath
    $out = New-Object System.Collections.Generic.List[string]
    $seenAllowed = $false
    $seenCsrf = $false

    foreach ($line in $lines) {
        if ($line -match "^\s*DJANGO_ALLOWED_HOSTS=") {
            $out.Add("DJANGO_ALLOWED_HOSTS=$allowed")
            $seenAllowed = $true
            continue
        }
        if ($line -match "^\s*DJANGO_CSRF_TRUSTED_ORIGINS=") {
            $out.Add("DJANGO_CSRF_TRUSTED_ORIGINS=$origin")
            $seenCsrf = $true
            continue
        }
        $out.Add($line)
    }
    if (-not $seenAllowed) { $out.Add("DJANGO_ALLOWED_HOSTS=$allowed") }
    if (-not $seenCsrf) { $out.Add("DJANGO_CSRF_TRUSTED_ORIGINS=$origin") }

    Write-EnvFileUtf8NoBom -Lines $out.ToArray()
    Show-PublicUrl -TunnelHost $TunnelHost

    if ($OnPublicUrlReady) {
        & $OnPublicUrlReady $TunnelHost
    }
}

function Get-SshLineText {
    param($Item)

    if ($Item -is [System.Management.Automation.ErrorRecord]) {
        if ($Item.ErrorDetails -and $Item.ErrorDetails.Message) {
            return $Item.ErrorDetails.Message.Trim()
        }
        return ""
    }
    return [string]$Item
}

function Should-PrintTunnelLine {
    param([string]$Line)

    if ($Line -match "\x1b\[") { return $false }
    if ($Line -match "^\s*$") { return $false }
    foreach ($n in @(
            "Welcome to localhost.run",
            "your connection id is",
            "Open your tunnel address",
            "To set up and manage",
            "To explore using",
            "forever-free",
            "create an account"
        )) {
        if ($Line -like "*$n*") { return $false }
    }
    return $true
}

function Invoke-TunnelLine {
    param(
        [string]$Line,
        [ref]$EnvUpdated,
        [ref]$PublicHost
    )

    if ($Line -match "https://([a-zA-Z0-9.-]+\.lhr\.life)") {
        $hostName = $Matches[1]
        if (-not $EnvUpdated.Value) {
            Set-DjangoTunnelHost -TunnelHost $hostName
            $EnvUpdated.Value = $true
            $PublicHost.Value = $hostName
        }
        return
    }

    if ($Line -eq "" -or -not $EnvUpdated.Value) {
        return
    }

    if (Should-PrintTunnelLine -Line $Line) {
        Write-Host $Line
    }
}

Ensure-EnvFile

Write-Host "Starting temporary tunnel (Ctrl+C to stop)."
Write-Host "Connecting to localhost.run..."
Write-Host ""

$envUpdated = $false
$publicHost = $null

ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=60 `
    -R 80:127.0.0.1:8000 nokey@localhost.run 2>&1 | ForEach-Object {
    $line = Get-SshLineText $_
    Invoke-TunnelLine -Line $line -EnvUpdated ([ref]$envUpdated) -PublicHost ([ref]$publicHost)
}

if (-not $envUpdated) {
    Write-Host ""
    Write-Host "Tunnel failed before a public URL was assigned." -ForegroundColor Red
    Write-Host "Check that ssh can reach localhost.run and Django is on port 8000." -ForegroundColor Yellow
    exit 1
}

if ($publicHost) {
    Show-PublicUrl -TunnelHost $publicHost
    Write-Host "Tunnel closed. Public URL is no longer active." -ForegroundColor Yellow
}
