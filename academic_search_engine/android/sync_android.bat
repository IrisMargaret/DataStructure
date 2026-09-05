@echo off
rem ============================================================
rem  sync_android.bat —— 把项目源码同步进 android 工程
rem  1) Python 包（core/service/web/ingest/crawler/agent + logutil.py）
rem     -> app/src/main/python/
rem  2) 前端与数据（templates/static/data 词典与元数据，不含 31MB 原文 PDF）
rem     -> app/src/main/assets/academic/
rem ============================================================
setlocal
set SRC=%~dp0..
set DST=%~dp0app\src\main

echo [1/3] 同步 Python 包到 app/src/main/python ...
for %%P in (core service web ingest crawler agent) do (
  if exist "%SRC%\%%P" (
    if exist "%DST%\python\%%P" rd /s /q "%DST%\python\%%P"
    xcopy /e /i /q /y "%SRC%\%%P" "%DST%\python\%%P" >nul
  ) else (
    echo   [warn] 缺少包目录: %%P
  )
)
if exist "%SRC%\logutil.py" copy /y "%SRC%\logutil.py" "%DST%\python\logutil.py" >nul

echo [2/3] 清理 __pycache__ ...
for /d /r "%DST%\python" %%D in (__pycache__) do rd /s /q "%%D" 2>nul

echo [3/3] 同步前端与数据到 app/src/main/assets/academic ...
if exist "%DST%\assets\academic" rd /s /q "%DST%\assets\academic"
mkdir "%DST%\assets\academic" 2>nul
xcopy /e /i /q /y "%SRC%\templates" "%DST%\assets\academic\templates" >nul
xcopy /e /i /q /y "%SRC%\static" "%DST%\assets\academic\static" >nul
mkdir "%DST%\assets\academic\data" 2>nul
for %%F in (papers.json bilingual.json stopwords.txt) do (
  if exist "%SRC%\data\%%F" copy /y "%SRC%\data\%%F" "%DST%\assets\academic\data\%%F" >nul
)

echo 同步完成。
endlocal
