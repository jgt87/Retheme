# AGENTS.md

Canonical notes for anyone (human or agent) changing Retheme. `README.md` is the
user guide; `PRODUCT.md` / `DESIGN.md` own product intent and visual rules.

## What this is
A local, Windows-first tool that (1) extracts a "brandkit" (template package)
from a PowerPoint template and (2) rethemes a content deck onto it, producing a
native, editable PPTX plus an HTML preview. Python 3.10+, FastAPI + one static
page, python-pptx + lxml. Runs on 127.0.0.1; nothing leaves the machine.

## Commands
```bash
pip install -r requirements.txt            # app
pip install -r requirements-dev.txt        # + pytest, playwright, axe
python -m pytest -q tests/                 # fast suite (all offline, ~20 s)
python -m pytest -q tests/test_retheme.py::test_palette_harmonization   # one test
python -m playwright install chromium      # once, for e2e/screenshots
python -m pytest -q e2e/                   # browser smoke + axe (port 8765)
python scripts/screenshots.py              # regenerate docs/screenshots/
python -m pptx_template_tool.cli serve     # UI on http://127.0.0.1:8000
python -m pptx_template_tool.cli audit template.potx package/   # fidelity check
scripts\build-portable.cmd [-Only exe|ps]  # portable packages into dist\
```
`RETHEME_E2E_CHANNEL=msedge` (or `--channel msedge` for the screenshot script)
uses the installed Edge instead of downloading Chromium.

## Architecture
- `extractor/` template -> package. `extract.py` orchestrates; `theme.py`
  colors/fonts + role inference; `layouts.py` placeholders, inheritance,
  backgrounds; `assets.py` image/shape assets + dedupe; `svg_convert.py`
  OOXML geometry -> SVG; `classify.py` asset-type heuristics; `grid.py`
  margins; `preview.py` LibreOffice or schematic previews; `package.py` writes
  `template.json` and derives `template.md` from it; `audit.py` independent
  fidelity walker.
- `application/` package + content -> output. `retheme.py` copies content
  slides wholesale into the brand template (the native path); `conflicts.py`
  finds where deck and brandkit differ and builds the choices; `generator.py`
  HTML deck; `pptx_generator.py` rebuild path for packages without an embedded
  source; `content_extract.py` deck -> content JSON; `preview_render.py`
  HTML preview from a rethemed deck.
- `webapp/app.py` FastAPI API + serves `static/` (`index.html`, `tokens.css`,
  `app.css`, `app.js`, `icon.svg` through an allow-list route).
- `cli.py` extract / apply / content / restyle / audit / serve.
- `tests/` fast pytest suite, synthetic fixtures only (`tests/fixtures/`);
  `e2e/` browser smoke test + shared driver (`flow.py`) also used by
  `scripts/screenshots.py`.

## Invariants (do not relax)
- **Never silently drop or change content.** Anything retained, converted,
  approximated or skipped is reported as a warning in user terms. Reason: the
  rebuild path once lost pictures in the PPTX while the preview showed them
  (78d4dbb); the fallback is now flagged `APPROXIMATE OUTPUT` (cd202df).
- **`template.md` is derived from `template.json`**, never edited on its own.
  Corrections rewrite the JSON and regenerate the markdown.
- **Bind to localhost and keep the Origin guard exact-host.** The API is
  unauthenticated; `_is_local_origin` parses the Origin. Reason: the first
  version prefix-matched, so `http://localhost.evil.example` passed (fixed
  2026-11-08, test `test_lookalike_local_origins_rejected`).
- **Static files go through the `UI_ASSETS` allow-list**, not a directory
  mount, so nothing else in the package is fetchable.
- **Colors and font sizes live in `static/tokens.css` only.**
  `tests/test_design_rules.py` fails on hex literals or off-scale sizes in
  `index.html`, `app.css`, `app.js`. Deck/user colors are built at runtime.
- **Every form control has an accessible name; status lines use
  `role="status"`, error boxes `role="alert"`.** The e2e axe scan fails on
  violations of impact moderate or higher.
- **No real company templates or branding in the repo, tests or screenshots.**
  Use `tests/fixtures/lumen_template.py` (fictional). Reason: the repo is public.
- **One version carrier:** `pptx_template_tool/__init__.py` `__version__`. The
  UI pill and the extractor stamp read it; don't hard-code it elsewhere.

## Conventions and gotchas
- The page must also work opened from disk (it shows a "start the server"
  message), so asset links in `index.html` are relative (`app.css`, not
  `/static/app.css`).
- `.gitignore`: ignore only bytecode `*.py[co]`, never `*.pyd`, and anchor venv
  rules to the root. Reason: the old patterns dropped 89 native modules from the
  bundled runtime (04dfdeb).
- `dist/` is build output, published as GitHub Release assets, never committed.
- PowerShell scripts target Windows PowerShell 5.1: ASCII only, and run native
  tools through `Invoke-Native` (5.1 turns native stderr into errors).
- E2E and screenshots use port 8765 so they never hit a running instance on 8000.
- Copy in the UI: plain, literal, no em dashes in new strings.

## Releasing
1. Bump `__version__` in `pptx_template_tool/__init__.py`.
2. Move `CHANGELOG.md` `Unreleased` to `## [X.Y.Z] - YYYY-MM-DD`.
3. `python -m pytest -q tests/` and `python -m pytest -q e2e/`.
4. Commit, `git tag -a vX.Y.Z -m "vX.Y.Z"`, push the tag. The `release`
   workflow builds both portable packages on Windows, zips them, writes
   `SHA256SUMS.txt` and creates the GitHub Release.

## Keeping docs in step
- User-visible change: add a line under `## [Unreleased]` in `CHANGELOG.md`.
- UI change: re-run `python scripts/screenshots.py` if the README screenshots
  would no longer match.
- New module or command: update Architecture / Commands here and the README.

<!-- Add your project instructions above or below the Repowise section. Repowise only updates the managed section between markers. -->

<!-- REPOWISE_DISTILL:START — Do not edit below this line. Auto-generated by Repowise. -->
### Output Distillation

- Prefer `repowise distill <cmd>` for noisy commands: test runs, builds, `git status`/`log`/`diff`, searches, file listings. It runs the command unchanged (exit code preserved) and prints a compact, errors-first rendering; every error line survives.
- Output may contain a marker like `[repowise#a1b2c3d4e5f6: 230 lines omitted (~6.1k tokens); restore: repowise expand a1b2c3d4e5f6]`. The omitted content is fully preserved: run `repowise expand <ref>` to retrieve it, or `repowise expand <ref> -q <regex>` for just the matching lines.
- Never re-run a command to see omitted output; expand the marker instead.
- For structure-level questions about a large indexed file ("what's in here", "which function handles X"), `get_context(["path"], include=["skeleton"])` returns the file with bodies elided (every signature plus the bodies of the most central symbols) at a fraction of the cost of a full Read.
<!-- REPOWISE_DISTILL:END -->
