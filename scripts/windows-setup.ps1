[CmdletBinding()]
param([string]$DependenciesPath, [string]$Generator)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$depsRoot = Join-Path $repoRoot '.deps'
if (!$DependenciesPath) {
    $DependenciesPath = Join-Path $depsRoot 'dhewm3-libs/x86_64-w64-mingw32'
    if (!(Test-Path -LiteralPath $DependenciesPath)) {
        # Fixed upstream revision: do not silently change dependency binaries.
        $revision = '57c565984c41356e8b1c4d31f182e763b6ea210a'
        New-Item -ItemType Directory -Force -Path $depsRoot | Out-Null
        $archive = Join-Path $depsRoot 'dhewm3-libs.zip'
        Invoke-WebRequest "https://github.com/dhewm/dhewm3-libs/archive/$revision.zip" -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $depsRoot -Force
        Move-Item -LiteralPath (Join-Path $depsRoot "dhewm3-libs-$revision") -Destination (Join-Path $depsRoot 'dhewm3-libs')
    }
}
if (!(Test-Path -LiteralPath (Join-Path $DependenciesPath 'include/SDL2/SDL.h'))) {
    throw 'DependenciesPath must be the x86_64-w64-mingw32 folder from dhewm3-libs.'
}
$DependenciesPath = (Resolve-Path -LiteralPath $DependenciesPath).Path
$configureArgs = @('-S', (Join-Path $repoRoot 'neo'), '--preset', 'windows-x64', "-DDHEWM3LIBS=$DependenciesPath")
if ($Generator) { $configureArgs += @('-G', $Generator) }
& cmake @configureArgs
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed. Install Visual Studio C++ build tools and a Windows SDK; see docs/WINDOWS.md.' }
& cmake --build (Join-Path $repoRoot 'build-windows') --config RelWithDebInfo --parallel
if ($LASTEXITCODE -ne 0) { throw 'CMake build failed.' }
$outputDir = Join-Path $repoRoot 'build-windows/RelWithDebInfo'
Get-ChildItem -LiteralPath (Join-Path $DependenciesPath 'bin') -Filter '*.dll' | Copy-Item -Destination $outputDir
Write-Output "Built engine and staged runtime DLLs in $outputDir"
