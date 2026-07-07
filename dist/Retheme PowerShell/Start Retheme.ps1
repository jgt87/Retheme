# Retheme - PowerShell portable launcher.
# Keep this window open while you work; close it to stop the server.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "$here\app;$here\libs"
$env:PYTHONDONTWRITEBYTECODE = "1"
& "$here\runtime\python.exe" "$here\app\portable_main.py" @args
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "The tool exited with an error (see above)." -ForegroundColor Red
    Read-Host "Press Enter to close"
}
