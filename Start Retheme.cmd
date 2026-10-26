@echo off
rem Launcher for the self-contained portable Retheme.
rem No install, no admin, no Python needed: this hands off to the PowerShell
rem portable package in dist\, which carries its own signed Python runtime.
rem (To run from source instead, use "scripts\Start Retheme (dev).cmd".)

setlocal
set "RUNNER=%~dp0dist\Retheme PowerShell\Start Retheme.cmd"
if not exist "%RUNNER%" (
    echo Portable package not found at:
    echo   "%RUNNER%"
    echo.
    echo Build it first by running:  scripts\build-portable.cmd
    echo or extract the release zip from https://github.com/jgt87/Retheme/releases
    pause
    exit /b 1
)
call "%RUNNER%" %*
