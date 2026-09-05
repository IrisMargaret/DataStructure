# ===== One-click APK build (PowerShell) =====
# Usage : .\build_apk.ps1
# Output: app\build\outputs\apk\debug\app-debug.apk
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Resolve-Py312 {
  $candidates = @(
    $env:ACADEMIC_PYTHON,
    "$env:LOCALAPPDATA/Programs/Python/Python312/python.exe",
    "$env:ProgramFiles/Python312/python.exe"
  ) | Where-Object { $_ -and (Test-Path $_) }
  if ($candidates) { return $candidates | Select-Object -First 1 }
  $cmd = Get-Command py -ErrorAction SilentlyContinue
  if ($cmd) {
    $out = & py -3.12 -c "import sys;print(sys.executable)" 2>$null
    if ($out) { $p = ($out | Select-Object -Last 1).Trim(); if (Test-Path $p) { return $p } }
  }
  return $null
}
$py = Resolve-Py312
if (-not $py) { throw "Python 3.12 not found. Install it or set ACADEMIC_PYTHON." }
Write-Host "[0] build python: $py"

$lp = Join-Path $root "local.properties"
$safePy = $py.Replace([char]92, "/")
if (Test-Path $lp) {
  $hasPy = Select-String -Path $lp -SimpleMatch -Quiet "python.executable="
  if (-not $hasPy) { Add-Content -Path $lp -Value ("python.executable=" + $safePy) -Encoding ascii }
} else {
  Set-Content -Path $lp -Value ("python.executable=" + $safePy) -Encoding ascii
}

# jieba wheel: PyPI has sdist only; Chaquopy pip requires wheels
$wheelDir = Join-Path $root "local-wheels"
$wheel = Get-ChildItem $wheelDir -Filter "jieba-*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $wheel) {
  New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
  Write-Host "[1] generating jieba wheel (network needed) ..."
  & $py -m pip wheel --no-deps --no-cache-dir --disable-pip-version-check --no-warn-script-location -w $wheelDir jieba==0.42.1
  if ($LASTEXITCODE -ne 0) { throw "jieba wheel generation failed" }
} else { Write-Host "[1] jieba wheel: $($wheel.Name)" }

# debug keystore (regenerate if missing)
$ks = Join-Path $root "app/debug.keystore"
if (-not (Test-Path $ks)) {
  Write-Host "[2] generating debug keystore ..."
  $kt = Get-Command keytool -ErrorAction SilentlyContinue
  if (-not $kt) {
    foreach ($c in @("$env:JAVA_HOME/bin/keytool.exe",
                     "$env:ProgramFiles/Android/Android Studio/jbr/bin/keytool.exe",
                     "$env:LOCALAPPDATA/Programs/Android Studio/jbr/bin/keytool.exe")) {
      if (Test-Path $c) { $kt = Get-Item $c; break }
    }
  }
  if (-not $kt) { throw "keytool not found for debug keystore" }
  & $kt.Source -genkeypair -v -keystore $ks -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
  if ($LASTEXITCODE -ne 0) { throw "debug keystore generation failed" }
} else { Write-Host "[2] debug keystore exists" }

Write-Host "[3] syncing project sources ..."
& (Join-Path $root "sync_android.ps1")

Write-Host "[4] locating gradle ..."
$wrapper = Join-Path $root "gradlew.bat"
$candidates = @()
if (Test-Path $wrapper) { $candidates += $wrapper }
$dists = Join-Path $env:USERPROFILE ".gradle/wrapper/dists"
if (Test-Path $dists) {
  Get-ChildItem $dists -Recurse -Filter "gradle.bat" -ErrorAction SilentlyContinue |
    ForEach-Object { $candidates += $_.FullName }
}
$gradle = $candidates | Select-Object -First 1
if (-not $gradle) {
  $cmd = Get-Command gradle -ErrorAction SilentlyContinue
  if ($cmd) { $gradle = $cmd.Source }
}
if (-not $gradle) { throw "gradle not found. Install it or add gradlew.bat." }
Write-Host "[4] gradle: $gradle"

Write-Host "[5] gradle :app:assembleDebug ..."
$env:GRADLE_USER_HOME = Join-Path $root ".gradle-home"
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $gradle -p $root :app:assembleDebug --no-daemon
$gcode = $LASTEXITCODE
$ErrorActionPreference = $oldEap
if ($gcode -ne 0) { throw "gradle build failed (exit $gcode)" }

$apk = Join-Path $root "app/build/outputs/apk/debug/app-debug.apk"
if (Test-Path $apk) { Write-Host "APK ready: $apk" }
else { Write-Warning "APK not found at expected path." }