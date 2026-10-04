# Shared helpers; dot-source this file from a launcher or test.
function Test-Doom3Data {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    foreach ($index in 0..8) {
        $archive = Join-Path $Path ('base/pak{0:000}.pk4' -f $index)
        $item = Get-Item -LiteralPath $archive -ErrorAction SilentlyContinue
        if (!$item -or $item.PSIsContainer -or $item.Length -eq 0) { return $false }
    }
    return $true
}

function Get-Doom3SteamCandidates {
    param([string]$SteamRoot)
    if (!$SteamRoot) { return }
    $libraries = @($SteamRoot)
    $vdf = Join-Path $SteamRoot 'steamapps/libraryfolders.vdf'
    if (Test-Path -LiteralPath $vdf) {
        foreach ($line in Get-Content -LiteralPath $vdf) {
            if ($line -match '"path"\s*"([^"]+)"') {
                $libraries += $Matches[1].Replace('\\', '\')
            }
        }
    }
    foreach ($library in ($libraries | Select-Object -Unique)) {
        $manifest = Join-Path $library 'steamapps/appmanifest_9050.acf'
        $installDir = 'Doom 3'
        if (Test-Path -LiteralPath $manifest) {
            $content = Get-Content -LiteralPath $manifest -Raw
            if ($content -match '"installdir"\s*"([^"]+)"') { $installDir = $Matches[1] }
        }
        Join-Path $library "steamapps/common/$installDir"
    }
}
