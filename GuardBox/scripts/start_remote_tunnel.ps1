param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BinDir = Join-Path $ScriptDir 'bin'
$CloudflaredExe = Join-Path $BinDir 'cloudflared.exe'

Write-Host '==========================================================' -ForegroundColor Cyan
Write-Host ' GUARDBOX - SECURE REMOTE ACCESS TUNNEL LAUNCHER' -ForegroundColor Cyan
Write-Host '==========================================================' -ForegroundColor Cyan
Write-Host "Forwarding Target : http://localhost:$Port (FastAPI)" -ForegroundColor White

if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

$CloudflaredCmd = Get-Command 'cloudflared' -ErrorAction SilentlyContinue
if (($null -eq $CloudflaredCmd) -and (-not (Test-Path $CloudflaredExe))) {
    Write-Host "`n[+] cloudflared not found. Downloading official Windows binary..." -ForegroundColor Yellow
    $DownloadUrl = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $CloudflaredExe
    Write-Host "[OK] Download complete: $CloudflaredExe" -ForegroundColor Green
}

$ExeToRun = if ($null -ne $CloudflaredCmd) { 'cloudflared' } else { $CloudflaredExe }

Write-Host "`n[+] Starting outbound HTTPS tunnel to localhost:$Port..." -ForegroundColor Green
Write-Host "[!] Copy the generated https://*.trycloudflare.com endpoint and enter it into GuardBox Android app in REMOTE mode.`n" -ForegroundColor Yellow

$TargetUrl = "http://localhost:$Port"
& $ExeToRun tunnel --url $TargetUrl
