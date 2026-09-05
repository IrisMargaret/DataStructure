# Sync project sources into the Android project.
# 1) Python packages (core/service/web/ingest/crawler/agent + logutil.py)
#    -> app/src/main/python/
# 2) Frontend & data (templates/static + data jsons, NO 31MB paper PDFs)
#    -> app/src/main/assets/academic/
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot '..'      # academic_search_engine root
$dstPython = Join-Path $PSScriptRoot 'app\src\main\python'
$dstAssets = Join-Path $PSScriptRoot 'app\src\main\assets\academic'

Write-Host '[1/3] syncing python packages -> src/main/python'
foreach ($pkg in @('core','service','web','ingest','crawler','agent')) {
    $s = Join-Path $src $pkg
    $d = Join-Path $dstPython $pkg
    if (Test-Path $s) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force }
        Copy-Item $s $d -Recurse
    } else { Write-Warning "missing package: $pkg" }
}
Copy-Item (Join-Path $src 'logutil.py') (Join-Path $dstPython 'logutil.py') -Force
Copy-Item (Join-Path $src 'paths.py') (Join-Path $dstPython 'paths.py') -Force

Write-Host '[2/3] removing __pycache__'
Get-ChildItem $dstPython -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '[3/3] syncing templates/static/data -> assets/academic'
if (Test-Path $dstAssets) { Remove-Item $dstAssets -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dstAssets | Out-Null
Copy-Item (Join-Path $src 'templates') (Join-Path $dstAssets 'templates') -Recurse
Copy-Item (Join-Path $src 'static') (Join-Path $dstAssets 'static') -Recurse
$dataDir = Join-Path $dstAssets 'data'
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
foreach ($f in @('papers.json','bilingual.json','stopwords.txt')) {
    $sf = Join-Path $src "data\$f"
    if (Test-Path $sf) { Copy-Item $sf (Join-Path $dataDir $f) -Force }
}
# safety: drop any runtime-artifact dirs that may linger
foreach ($junk in @('logs','uploads','papers_files')) {
    $p = Join-Path $dstAssets $junk
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}
Write-Host 'sync done.'
