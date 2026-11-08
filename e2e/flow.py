"""Shared browser driver for the smoke test and the screenshot script.

Starts the real server on a dedicated test port (never 8000, so it cannot
collide with a running instance) and walks the three surfaces:
extract -> review -> retheme choices -> preview.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from pathlib import Path
from typing import Callable

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
TEST_PORT = 8765
DEMO_DECK = ROOT / "examples" / "demo-content.pptx"


@contextlib.contextmanager
def running_server(port: int = TEST_PORT):
    from pptx_template_tool.webapp.app import app

    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"port {port} is already in use")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def walk(page, base_url: str, template: Path,
         on_surface: Callable[[str], None], deck: Path = DEMO_DECK) -> None:
    """Drive the full workflow, calling on_surface(name) at each stop:
    home, review, apply, choices (if the deck needs decisions), result."""
    page.goto(base_url)
    page.wait_for_selector("#dropzone")
    on_surface("home")

    page.set_input_files("#file-input", str(template))
    page.wait_for_selector("#review:not(.hidden)", timeout=120_000)
    page.wait_for_function("(document.querySelector('#layout-preview img') || {}).complete")
    on_surface("review")

    page.click("#goto-apply-btn")
    page.set_input_files("#content-file", str(deck))
    assert page.is_checked("#bk-session")
    on_surface("apply")

    page.click("#apply-btn")
    page.wait_for_selector("#choices-card:not(.hidden), #tab-preview:not(.hidden)",
                           timeout=120_000)
    if page.is_visible("#choices-card"):
        page.wait_for_function(
            "document.querySelector('#choices-frame').srcdoc.length > 0", timeout=60_000)
        page.wait_for_timeout(500)  # let the frame lay out before measuring
        on_surface("choices")
        page.click("#confirm-btn")
        page.wait_for_selector("#tab-preview:not(.hidden)", timeout=120_000)
    page.wait_for_function(
        "(() => { const d = document.querySelector('#preview-frame').contentDocument;"
        " return d && d.querySelectorAll('.slide').length > 0; })()", timeout=60_000)
    page.wait_for_timeout(500)
    on_surface("result")
