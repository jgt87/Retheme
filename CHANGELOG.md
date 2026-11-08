# Changelog

All notable changes to Retheme. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- **A website could pass itself off as local.** The server's cross-site
  request guard accepted any origin that merely started with `http://localhost`
  (for example `http://localhost.evil.example`). It now checks the exact host.
- Screen readers now announce extraction progress, save/apply status and
  errors, and every upload field, role selector and position field has a name.
- Smooth scrolling now respects the system's "reduce motion" setting.
- The browser tab shows a Retheme icon (it used to request a missing
  `favicon.ico`).
- **A failed template upload no longer strands you.** The error appears under
  the drop zone in plain words (not raw JSON) and you can pick another file
  right away; the page no longer needs a reload. Non-PowerPoint files dropped
  on the page are refused before uploading.
- The header no longer overlaps itself in narrow windows or at high zoom.
- Hovering the help button while the help page is open no longer hides the "?".
- The extracted brandkit is shown under the template's own name instead of
  "(source)".

### Changed
- Review page: **Apply this brandkit** is now the main button. **Save
  corrections** stays disabled until you change something and shows how many
  corrections it will save.
- "N items need review" is a link that jumps to the first flagged asset.
- Plain-language labels in the review tables (for example "Dark 1 (dk1)",
  "Decorative shape"), title-case table headers.
- The result page always ends with a summary ("7 slides rethemed. No
  warnings: all content was retained.") and offers **Retheme another deck**,
  which keeps the brandkit.
- Disabled buttons show a "not allowed" cursor.
- Review flags read "⚠ verify" instead of an emoji alone.
- Numbers in tables and position fields line up (tabular figures); position
  fields are right-aligned.
- The web page is split into `tokens.css`, `app.css` and `app.js`.

### Added
- README screenshots, generated from a fictional template by
  `scripts/screenshots.py`.
- Browser smoke test (`e2e/`): runs the whole workflow and an accessibility
  scan (axe, WCAG 2.1 A/AA) on every screen.
- Design-rule test: colors and font sizes may only come from `tokens.css`.
- GitHub Actions: tests on every push; tagged releases build the portable
  packages with SHA-256 checksums.
- `AGENTS.md` project notes and this changelog.

## [0.3.0] - 2026-10-26

First public release (MIT). Earlier history is in the git log.
Published on GitHub under the tag `v0.1.0` although the app reports 0.3.0;
from the next release on, the tag must equal the app version (the release
workflow checks it).

### Added
- Per-slide protection in the apply choices (full retain or partial).
- Prominent `APPROXIMATE OUTPUT` warning when apply falls back to the rebuild
  path.

### Fixed
- Content-deck pictures were missing from the PPTX on the rebuild path.
- Portable packages failed after cloning (`No module named '_socket'`) because
  `.gitignore` dropped the bundled runtime's native modules.

### Changed
- Portable packages are published as GitHub Release assets instead of being
  committed under `dist/`.
