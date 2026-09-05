# ===== Desktop exe one-click build (PowerShell) =====
# Usage : .\build_exe.ps1
# Output: desktop\dist\AcademicSearchEngine.exe + 学术论文检索.exe (onefile, windowed)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Resolve-Py312 {
  $candidates = @(
    $env:ACADEMIC_PYTHON,
    "$env:LOCALAPPDATA/Programs/Python/Python312/python.exe",
    "$env:ProgramFiles/Python312/python.exe"
  ) | Where-Object { $_ -and (Test-Path $_) }
  if ($candidates) { return $candidates | Select-Object -First 1 }
  return $null
}
$py = Resolve-Py312
if (-not $py) { throw "Python 3.12 not found. Install it or set ACADEMIC_PYTHON." }
Write-Host "[1/4] python: $py"

$venv = Join-Path $root ".build-venv"
$vpy = Join-Path $venv "Scripts/python.exe"
if (-not (Test-Path $vpy)) {
  Write-Host "[1/4] creating build venv ..."
  & $py -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}

$depsOk = Join-Path $venv ".deps-ok"
if (-not (Test-Path $depsOk)) {
  Write-Host "[2/4] installing deps (pywebview/pyinstaller, network needed) ..."
  $req = Join-Path (Join-Path $root "..") "requirements.txt"
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $vpy -m pip install --disable-pip-version-check --timeout 90 -q -r $req pywebview pyinstaller pyinstaller-hooks-contrib
  $pipCode = $LASTEXITCODE
  $ErrorActionPreference = $oldEap
  if ($pipCode -ne 0) { throw "pip install failed" }
  Set-Content -Path $depsOk -Value "ok"
} else {
  Write-Host "[2/4] deps already installed"
}

Write-Host "[3/4] PyInstaller onefile ..."
$dist = Join-Path $root "dist"
$work = Join-Path $root "build"
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $vpy -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $root "academic_search.spec")
$piCode = $LASTEXITCODE
$ErrorActionPreference = $oldEap
if ($piCode -ne 0) { throw "PyInstaller build failed" }

Write-Host "[4/4] naming copy ..."
$exe = Join-Path $dist "AcademicSearchEngine.exe"
if (Test-Path $exe) {
  $cn = [string][char]0x5B66 + [char]0x672F + [char]0x8BBA + [char]0x6587 + [char]0x68C0 + [char]0x7D22
  $dest = Join-Path $dist ($cn + ".exe")
  Copy-Item $exe $dest -Force
  Write-Host "Desktop ready: $dest"
} else { throw "build output not found: AcademicSearchEngine.exe" }