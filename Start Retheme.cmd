@echo off
rem Double-click launcher for the Retheme web UI.
rem Starts the extraction server and opens your browser on it.
rem Keep this window open while you work - closing it stops the server.

setlocal
cd /d "%~dp0"
set PORT=8000
title Retheme - server (close this window to stop)

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.10+ from python.org
    echo and make sure "Add python to PATH" is checked during install.
    pause
    exit /b 1
)

python -c "import pptx, fastapi, uvicorn, jinja2, PIL, lxml, multipart" >nul 2>nul
if errorlevel 1 (
    echo First run: installing required packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Package installation failed - see the messages above.
        pause
        exit /b 1
    )
)

rem Open the browser once the server actually responds (max ~15 s).
start "" /min powershell -NoProfile -Command ^
  "for ($i=0; $i -lt 30; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/ -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process 'http://127.0.0.1:%PORT%/'"

echo.
echo Starting the Retheme on http://127.0.0.1:%PORT%/
echo Your browser will open automatically. Keep this window open while you work.
echo.
python -m pptx_template_tool.cli serve --port %PORT%

echo.
echo The server has stopped. If that was unexpected, the error is shown above.
pause
