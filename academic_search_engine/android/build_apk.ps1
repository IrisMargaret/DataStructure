# ===== One-click APK build (PowerShell) =====
# Usage:  .\build_apk.ps1
# Output: app\build\outputs\apk\debug\app-debug.apk
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Write-Host '[1/3] syncing project sources ...'
& (Join-Path $root 'sync_android.ps1')

Write-Host '[2/3] locating gradle ...'
# Prefer a wrapper if present; else reuse the unpacked local distribution
# (android studio style cache), else fall back to PATH.
$wrapper = Join-Path $root 'gradlew.bat'
$candidates = @()
if (Test-Path $wrapper) { $candidates += $wrapper }
$dists = Join-Path $env:USERPROFILE '.gradle\wrapper\dists'
if (Test-Path $dists) {
    Get-ChildItem $dists -Recurse -Filter 'gradle.bat' -ErrorAction SilentlyContinue |
        ForEach-Object { $candidates += $_.FullName }
}
$gradle = $candidates | Select-Object -First 1
if (-not $gradle) {
    $cmd = Get-Command gradle -ErrorAction SilentlyContinue
    if ($cmd) { $gradle = $cmd.Source }
}
if (-not $gradle) { throw 'Cannot find gradle. Install it or add gradlew.bat.' }
Write-Host "using gradle: $gradle"

Write-Host '[3/3] gradle :app:assembleDebug (first run downloads deps) ...'
$env:GRADLE_USER_HOME = Join-Path $root '.gradle-home'
& cmd /c "`"$gradle`" -p `"$root`" :app:assembleDebug --no-daemon"
if ($LASTEXITCODE -ne 0) { throw "gradle build failed (exit $LASTEXITCODE)" }

$apk = Join-Path $root 'app\build\outputs\apk\debug\app-debug.apk'
if (Test-Path $apk) { Write-Host "APK ready: $apk" }
else { Write-Warning 'APK not found at expected path.' }
