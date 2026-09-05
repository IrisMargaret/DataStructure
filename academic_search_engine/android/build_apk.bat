@echo off
rem One-click APK build (debug). Output: app-debug.apk
setlocal
cd /d "%~dp0"

echo [1/3] syncing project sources ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_android.ps1"
if errorlevel 1 goto fail

echo [2/3] locating gradle ...
if exist "%~dp0gradlew.bat" (
  set GRADLE_CMD=call "%~dp0gradlew.bat"
) else (
  set GRADLE_CMD=call "%~dp0gradle.bat"
)

echo [3/3] building assembleDebug (first run downloads deps, be patient) ...
%GRADLE_CMD% :app:assembleDebug --no-daemon
if errorlevel 1 goto fail

echo.
echo APK: app\build\outputs\apk\debug\app-debug.apk
exit /b 0

:fail
echo BUILD FAILED - see log above.
exit /b 1
