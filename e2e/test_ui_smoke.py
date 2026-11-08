"""Browser smoke test: the whole UI workflow in a real browser, with an
axe-core WCAG A/AA scan of every surface and no console errors.

Not part of the fast suite (`pytest tests/`). Run it with:

    pip install -r requirements-dev.txt
    python -m playwright install chromium     # or set RETHEME_E2E_CHANNEL=msedge
    python -m pytest e2e/
"""

from __future__ import annotations

import os

import pytest

playwright = pytest.importorskip("playwright.sync_api")
axe_mod = pytest.importorskip("axe_playwright_python.sync_playwright")

from e2e.flow import running_server, walk  # noqa: E402
from tests.fixtures.lumen_template import build  # noqa: E402

# Impact levels that fail the test. "minor" findings are reported, not fatal.
FAIL_IMPACTS = {"critical", "serious", "moderate"}


def test_workflow_is_accessible_and_error_free(tmp_path):
    template = build(tmp_path / "lumen-template.pptx")
    axe = axe_mod.Axe()
    problems: list[str] = []
    console_errors: list[str] = []

    with running_server() as url, playwright.sync_playwright() as p:
        channel = os.environ.get("RETHEME_E2E_CHANNEL") or None
        browser = p.chromium.launch(channel=channel)
        # reduced motion: axe must not sample colors mid-transition
        page = browser.new_page(viewport={"width": 1400, "height": 900},
                                reduced_motion="reduce")
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        def check(surface: str) -> None:
            result = axe.run(page, options={
                "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21aa"]}})
            for v in result.response["violations"]:
                if v["impact"] in FAIL_IMPACTS:
                    targets = [n["target"] for n in v["nodes"]][:3]
                    problems.append(f"[{surface}] {v['id']} ({v['impact']}): "
                                    f"{v['help']} -> {targets}")

        walk(page, url, template, check)
        browser.close()

    assert not console_errors, "console errors:\n" + "\n".join(console_errors)
    assert not problems, "accessibility violations:\n" + "\n".join(problems)
