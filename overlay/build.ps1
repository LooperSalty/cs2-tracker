<#
.SYNOPSIS
    Construit CS2TrackerOverlay.exe.

.DESCRIPTION
    Localise CMake et le toolset MSVC via vswhere, configure puis compile en
    Release. L'executable produit est autonome : la runtime C++ est liee
    statiquement, aucun redistribuable n'est requis sur la machine cible.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File overlay\build.ps1
#>

[CmdletBinding()]
param(
    [string]$Generator = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

Write-Host "=== Overlay CS2 Tracker — construction ===" -ForegroundColor Cyan

function Find-CMake {
    $inPath = Get-Command cmake -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }

    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $vs = & $vswhere -latest -products * -property installationPath
        if ($vs) {
            $bundled = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
            if (Test-Path $bundled) { return $bundled }
        }
    }
    throw "CMake introuvable. Installe-le, ou installe la charge de travail 'Developpement Desktop en C++' de Visual Studio."
}

function Resolve-Generator {
    if ($Generator) { return $Generator }

    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { throw "Visual Studio introuvable." }

    $version = & $vswhere -latest -products * -property catalog_productLineVersion
    $major = & $vswhere -latest -products * -property installationVersion
    $majorNumber = ($major -split '\.')[0]

    switch ($majorNumber) {
        "18" { return "Visual Studio 18 2026" }
        "17" { return "Visual Studio 17 2022" }
        "16" { return "Visual Studio 16 2019" }
        default { throw "Version de Visual Studio non reconnue ($major, ligne $version)." }
    }
}

$cmake = Find-CMake
$gen = Resolve-Generator
Write-Host "CMake     : $cmake"
Write-Host "Generateur: $gen"

if ($Clean -and (Test-Path "build")) {
    Write-Host "`nNettoyage..." -ForegroundColor Yellow
    Remove-Item "build" -Recurse -Force
}

Write-Host "`n[1/2] Configuration..." -ForegroundColor Yellow
& $cmake -S . -B build -G $gen -A x64
if ($LASTEXITCODE -ne 0) { throw "Configuration CMake echouee." }

Write-Host "`n[2/2] Compilation..." -ForegroundColor Yellow
& $cmake --build build --config Release
if ($LASTEXITCODE -ne 0) { throw "Compilation echouee." }

$exe = Join-Path $root "build\Release\CS2TrackerOverlay.exe"
if (-not (Test-Path $exe)) { throw "Executable introuvable : $exe" }

$sizeKb = [math]::Round((Get-Item $exe).Length / 1KB, 0)
Write-Host "`nTermine : $exe ($sizeKb Ko)" -ForegroundColor Green
Write-Host "Lance CS2 Tracker, puis cet executable. F8 masque, F9 deplace, Ctrl+Maj+F8 quitte."
