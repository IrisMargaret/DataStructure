@echo off
rem One-click APK build (debug). Output: app-debug.apk
rem 统一入口：内部调用 build_apk.ps1（含 python/wheel/keystore 自举）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_apk.ps1"
exit /b %errorlevel%