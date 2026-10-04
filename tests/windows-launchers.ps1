$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../scripts/windows-lib.ps1"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
function Assert-True($Condition, $Message) {
    if (!$Condition) { throw $Message }
}
try {
    $library = Join-Path $testRoot 'Extra Library'
    $game = Join-Path $library 'steamapps/common/Custom Doom Folder'
    New-Item -ItemType Directory -Force -Path "$game/base" | Out-Null
    foreach ($index in 0..8) {
        Set-Content -LiteralPath (Join-Path $game ('base/pak{0:000}.pk4' -f $index)) -Value 'fixture'
    }
    Assert-True (Test-Doom3Data $game) 'Complete data rejected'
    $missing = Join-Path $game 'base/pak008.pk4'
    Remove-Item -LiteralPath $missing
    Assert-True (!(Test-Doom3Data $game)) 'Missing archive accepted'
    [IO.File]::WriteAllBytes($missing, [byte[]]@())
    Assert-True (!(Test-Doom3Data $game)) 'Empty archive accepted'
    Set-Content -LiteralPath $missing -Value 'fixture'
    $steam = Join-Path $testRoot 'Steam'
    New-Item -ItemType Directory -Force -Path "$steam/steamapps" | Out-Null
    $escapedLibrary = $library.Replace('\', '\\')
    Set-Content -LiteralPath "$steam/steamapps/libraryfolders.vdf" -Value ('"path" "' + $escapedLibrary + '"')
    Set-Content -LiteralPath "$library/steamapps/appmanifest_9050.acf" -Value '"installdir" "Custom Doom Folder"'
    $candidates = @(Get-Doom3SteamCandidates $steam)
    Assert-True ($candidates -contains $game) 'Manifest install directory / escaped library path not discovered'
    & "$PSScriptRoot/../scripts/windows-run.ps1" -GameData $game -CheckOnly
    Write-Output 'Windows launcher regression tests passed.'
} finally {
    # The target is an absolute, unique child of the OS temporary directory.
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
        if (!$resolvedTestRoot.StartsWith($tempParent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove a test directory outside $tempParent"
        }
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
