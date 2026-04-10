# Build the scistack-gui extension on Windows local disk, then copy the
# compiled output back to the original location.
#
# This works around esbuild failing with EIO errors when building directly
# on a network mount. The resulting extension.js is platform-independent,
# so building on Windows and running on Linux (via Remote-SSH) is fine.
#
# Usage (from this script's directory):
#   powershell -ExecutionPolicy Bypass -File .\build-on-windows.ps1

$ErrorActionPreference = "Stop"

# Source = the directory this script lives in.
$SourceDir = $PSScriptRoot
if (-not $SourceDir) { $SourceDir = (Get-Location).Path }

# Build in local %TEMP% to avoid the network mount.
$BuildDir = Join-Path $env:TEMP "scistack-ext-build"

Write-Host "Source: $SourceDir"
Write-Host "Build:  $BuildDir"
Write-Host ""

# ---- clean the local build dir ------------------------------------------------
if (Test-Path $BuildDir) {
    Write-Host "Removing old build directory..."
    Remove-Item -Recurse -Force $BuildDir
}

# ---- copy source to local disk (skip node_modules + dist) --------------------
Write-Host "Copying source to local disk..."
New-Item -ItemType Directory -Path $BuildDir | Out-Null

# robocopy is the fastest reliable way on Windows; /XD excludes directories.
robocopy $SourceDir $BuildDir /E /XD node_modules dist /NFL /NDL /NJH /NJS /NP | Out-Null
# robocopy exit codes 0-7 are success; 8+ are failure.
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

# ---- npm install + build ------------------------------------------------------
Push-Location $BuildDir
try {
    Write-Host ""
    Write-Host "Running npm install..."
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

    Write-Host ""
    Write-Host "Running npm run build..."
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
    Pop-Location
}

# ---- copy dist/ back to the network mount ------------------------------------
$SourceDist = Join-Path $SourceDir "dist"
$BuiltDist  = Join-Path $BuildDir  "dist"

if (-not (Test-Path $SourceDist)) {
    New-Item -ItemType Directory -Path $SourceDist | Out-Null
}

Write-Host ""
Write-Host "Copying dist/ back to source..."
Copy-Item -Force (Join-Path $BuiltDist "extension.js") (Join-Path $SourceDist "extension.js")

$MapFile = Join-Path $BuiltDist "extension.js.map"
if (Test-Path $MapFile) {
    Copy-Item -Force $MapFile (Join-Path $SourceDist "extension.js.map")
}

Write-Host ""
Write-Host "Done. Reload the VS Code window to pick up the new extension.js."
