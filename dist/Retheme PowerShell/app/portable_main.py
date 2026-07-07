"""Entry point for the portable (PyInstaller) build.

Double-click behavior: start the web UI on a free port and open the browser.
With CLI arguments it behaves exactly like `python -m pptx_template_tool.cli`,
so the portable exe also covers extract/apply/restyle/audit:

    "Retheme.exe" extract template.potx -o package/
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser


def _wait_and_open(port: int) -> None:
    import urllib.request
    url = f"http://127.0.0.1:{port}/"
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(url)


def _free_port(preferred: int = 8000) -> int:
    for port in (preferred, 8010, 8020, 8080):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 0  # let the OS pick


def main() -> None:
    if len(sys.argv) > 1:
        from pptx_template_tool.cli import main as cli_main
        sys.exit(cli_main(sys.argv[1:]))

    port = _free_port()
    threading.Thread(target=_wait_and_open, args=(port,), daemon=True).start()

    import uvicorn
    from pptx_template_tool.webapp.app import app

    print(f"Retheme - http://127.0.0.1:{port}/")
    print("Your browser will open automatically. "
          "Keep this window open while you work; close it to stop.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
