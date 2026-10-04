[CmdletBinding()]
param(
    [string]$GameData,
    [string]$Binary,
    [switch]$CheckOnly,
    [string[]]$EngineArgs = @()
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-lib.ps1"
$repoRoot = Split-Path $PSScriptRoot -Parent
$prefsFile = Join-Path $env:APPDATA 'dhewm3/gamepath'

if ($GameData) {
    if (!(Test-Doom3Data $GameData)) {
        throw 'GameData must contain nonempty base/pak000.pk4 through pak008.pk4 (original Doom 3).'
    }
} else {
    $candidates = @()
    if (Test-Path -LiteralPath $prefsFile) { $candidates += (Get-Content -LiteralPath $prefsFile -Raw).Trim() }
    $steamRoot = (Get-ItemProperty 'HKCU:/Software/Valve/Steam' -ErrorAction SilentlyContinue).SteamPath
    $candidates += @(Get-Doom3SteamCandidates $steamRoot)
    $GameData = $candidates | Where-Object { Test-Doom3Data $_ } | Select-Object -First 1
    if (!$GameData) { throw 'Doom 3 data not found. Install original DOOM 3 (Steam app 9050), or supply -GameData.' }
}
$GameData = (Resolve-Path -LiteralPath $GameData).Path
Write-Output "Doom 3 data: $GameData"
Write-Output 'Base game: all nine required archives present and nonempty.'
if (!(Test-Path -LiteralPath (Join-Path $GameData 'd3xp/pak000.pk4') -PathType Leaf)) {
    Write-Warning 'Resurrection of Evil data is missing; the base game can still run.'
}
if ($CheckOnly) { return }
if (!$Binary) { $Binary = Join-Path $repoRoot 'build-windows/RelWithDebInfo/dhewm3.exe' }
if (!(Test-Path -LiteralPath $Binary -PathType Leaf)) { throw "Engine not found: $Binary. Run scripts/windows-setup.ps1 first." }
New-Item -ItemType Directory -Force -Path (Split-Path $prefsFile -Parent) | Out-Null
Set-Content -LiteralPath $prefsFile -Value $GameData
& $Binary '+set' 'fs_basepath' $GameData @EngineArgs
if ($LASTEXITCODE -ne 0) { throw "Engine exited with code $LASTEXITCODE." }
