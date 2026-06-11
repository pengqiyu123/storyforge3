# Build StoryForge3 Python sidecar for Windows x86_64.
# Prerequisites: Python 3.11+, pip install pyinstaller
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_sidecar.ps1

$ErrorActionPreference = "Stop"
$TargetTriple = "x86_64-pc-windows-msvc"
$BinaryName = "storyforge3-api-$TargetTriple"
$OutputDir = "src-tauri/binaries"
$DestDir = "$OutputDir/$BinaryName"

Write-Host "Building StoryForge3 sidecar..."

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

pyinstaller scripts/storyforge3-api.spec `
    --workpath build/sidecar-work `
    --distpath build/sidecar-dist `
    --clean `
    --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit 1
}

$SourceDir = "build/sidecar-dist/storyforge3-api"

if (Test-Path $DestDir) {
    Remove-Item -Recurse -Force $DestDir
}
Copy-Item -Recurse $SourceDir $DestDir

$OldExe = "$DestDir/storyforge3-api.exe"
$NewExe = "$DestDir/$BinaryName.exe"
if (Test-Path $OldExe) {
    Move-Item -Force $OldExe $NewExe
}

Write-Host "Sidecar built successfully: $DestDir"
Write-Host "Main executable: $NewExe"

$Size = (Get-ChildItem -Recurse $DestDir | Measure-Object -Property Length -Sum).Sum
$SizeMB = [math]::Round($Size / 1MB, 1)
Write-Host "Sidecar size: $SizeMB MB"
