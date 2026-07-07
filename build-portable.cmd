@echo off
rem Rebuilds BOTH portable packages (see build-portable.ps1):
rem   dist\Retheme\             - exe bundle (PyInstaller)
rem   dist\Retheme PowerShell\  - no-exe bundle (signed Python)
rem Optional: pass "-Only exe" or "-Only ps" to build just one.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-portable.ps1" %*
if errorlevel 1 pause
