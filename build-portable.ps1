# Builds BOTH portable, zero-install packages:
#
#   1. dist\Retheme\            PyInstaller exe bundle
#   2. dist\Retheme PowerShell\ signed Python runtime + source,
#                                          PowerShell launcher (no compiled
#                                          exe - for machines that block
#                                          unsigned executables)
#
# Run via build-portable.cmd, or:
#   powershell -ExecutionPolicy Bypass -File build-portable.ps1 [-Only exe|ps]

param([ValidateSet("exe", "ps", "both")] [string]$Only = "both")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Invoke-Native([string]$cmdLine, [string]$what) {
    # PS 5.1 escalates native stderr chatter to errors under EAP=Stop when
    # output is redirected; run via cmd and judge by exit code instead.
    $eap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    cmd /c $cmdLine
    $code = $LASTEXITCODE
    $ErrorActionPreference = $eap
    if ($code -ne 0) { throw "$what failed (exit $code)" }
}

# ======================================================================
# Package 1: PyInstaller exe bundle
# ======================================================================
if ($Only -in "exe", "both") {
    Write-Host "=== Building exe package (PyInstaller) ===" -ForegroundColor Cyan
    & python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing PyInstaller..."
        Invoke-Native "python -m pip install --quiet pyinstaller" "pip install pyinstaller"
    }
    Invoke-Native ('python -m PyInstaller --noconfirm --clean ' +
        '--name "Retheme" ' +
        '--add-data "pptx_template_tool\webapp\static;pptx_template_tool\webapp\static" ' +
        '--collect-data pptx --collect-submodules uvicorn ' +
        '--hidden-import multipart portable_main.py') "PyInstaller"
    Write-Host "exe package: dist\Retheme\"
}

# ======================================================================
# Package 2: PowerShell-based bundle (no compiled exe)
# ======================================================================
if ($Only -in "ps", "both") {
    Write-Host "=== Building PowerShell package ===" -ForegroundColor Cyan
    $out = Join-Path $root "dist\Retheme PowerShell"
    $runtimeSrc = & python -c "import sys; print(sys.base_prefix)"

    if (Test-Path $out) { Remove-Item $out -Recurse -Force }
    New-Item -ItemType Directory -Force "$out\app" | Out-Null

    Write-Host "Copying Python runtime from $runtimeSrc ..."
    robocopy $runtimeSrc "$out\runtime" /E /NFL /NDL /NJH /NJS /NP `
        /XD tcl include libs Scripts test tests idle_test __pycache__ site-packages `
        /XF pythonw.exe BUILD | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy runtime failed ($LASTEXITCODE)" }

    Write-Host "Copying app source..."
    robocopy "$root\pptx_template_tool" "$out\app\pptx_template_tool" /E /NFL /NDL /NJH /NJS /NP `
        /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy app failed ($LASTEXITCODE)" }
    Copy-Item "$root\portable_main.py" "$out\app\"

    Write-Host "Installing dependencies into libs\ ..."
    Invoke-Native ("python -m pip install --quiet --target ""$out\libs"" " +
                   "-r ""$root\requirements.txt""") "pip install --target"
    Get-ChildItem "$out\libs" -Recurse -Directory -Filter __pycache__ |
        Remove-Item -Recurse -Force

    $ps1 = @'
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
'@
    Set-Content -Path "$out\Start Retheme.ps1" -Value $ps1 -Encoding utf8

    $cmd = @'
@echo off
rem Double-click convenience wrapper (double-clicking a .ps1 opens an editor).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start Retheme.ps1" %*
'@
    Set-Content -Path "$out\Start Retheme.cmd" -Value $cmd -Encoding ascii

    $readme = @'
Retheme - PowerShell portable package
================================================

No installation, no admin rights, no compiled executable:
- runtime\python.exe is an official signed CPython interpreter
- app\ is the tool's source code, libs\ its dependencies

Start (either works):
  * double-click "Start Retheme.cmd"
  * or in PowerShell:  .\'Start Retheme.ps1'

The web UI opens in your browser automatically. Close the console window
to stop the tool.

Command line (extract/apply/restyle/audit), e.g.:
  .\'Start Retheme.ps1' extract template.potx -o package\
'@
    Set-Content -Path "$out\README.txt" -Value $readme -Encoding utf8

    $size = "{0:N0} MB" -f ((Get-ChildItem $out -Recurse -File |
        Measure-Object Length -Sum).Sum / 1MB)
    Write-Host "PowerShell package: dist\Retheme PowerShell\ ($size)"
}

Write-Host ""
Write-Host "Done. Copy either folder from dist\ to any Windows machine." -ForegroundColor Green
