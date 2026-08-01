<#
.SYNOPSIS
    Construit CS2Tracker.exe.

.DESCRIPTION
    Installe les dependances de build si necessaire, lance PyInstaller, puis
    verifie que l'executable produit demarre reellement. Sans cette derniere
    verification, un module charge dynamiquement et oublie ne se manifesterait
    qu'entre les mains de l'utilisateur.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "=== CS2 Tracker — construction de l'executable ===" -ForegroundColor Cyan
Write-Host "Racine : $root"

if (-not $SkipInstall) {
    Write-Host "`n[1/4] Dependances..." -ForegroundColor Yellow
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Installation des dependances echouee." }
}

Write-Host "`n[2/4] Nettoyage..." -ForegroundColor Yellow
foreach ($dir in @("build", "dist")) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}

Write-Host "`n[3/4] PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller packaging/cs2tracker.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a echoue." }

$exe = Join-Path $root "dist\CS2Tracker.exe"
if (-not (Test-Path $exe)) { throw "Executable introuvable : $exe" }

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Executable produit : $exe ($sizeMb Mo)" -ForegroundColor Green

if (-not $SkipSmokeTest) {
    Write-Host "`n[4/4] Verification de demarrage..." -ForegroundColor Yellow

    $versionOutput = & $exe --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "L'executable ne repond pas a --version : $versionOutput" }
    Write-Host "  --version : $versionOutput"

    # Demarrage reel de l'API sur un port dedie, pour ne pas heurter une
    # instance de developpement deja lancee.
    $env:CS2T_API_PORT = "8699"
    $process = Start-Process -FilePath $exe -ArgumentList "--api-only" -PassThru -WindowStyle Hidden
    try {
        $ready = $false
        foreach ($attempt in 1..40) {
            Start-Sleep -Milliseconds 500
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:8699/health" -TimeoutSec 2 -UseBasicParsing
                if ($response.StatusCode -eq 200) { $ready = $true; break }
            } catch { }
        }
        if (-not $ready) { throw "L'API embarquee n'a pas repondu en 20 s." }
        Write-Host "  API : /health repond" -ForegroundColor Green

        $ui = Invoke-WebRequest -Uri "http://127.0.0.1:8699/app/" -TimeoutSec 5 -UseBasicParsing
        if ($ui.StatusCode -ne 200) { throw "L'interface web n'est pas servie." }
        Write-Host "  Interface web : servie" -ForegroundColor Green
    }
    finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        Remove-Item Env:\CS2T_API_PORT -ErrorAction SilentlyContinue
    }
}

Write-Host "`nTermine. Distribue dist\CS2Tracker.exe tel quel." -ForegroundColor Green
