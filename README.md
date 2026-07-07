# Retheme

**PPTX brandkit extraction & application — by JGT**

Implements `pptx-template-extractor-requirements.md`: a two-phase tool that
(1) extracts a **template package** from a PowerPoint template and
(2) applies that package to LLM-generated content to produce an HTML deck
that visually matches the original template, ready for HTML→PPTX conversion.

```
Template.pptx ──▶ EXTRACTION ──▶ template-package/ ──▶ APPLICATION ──▶ deck.html
                  (Phase 1)      ├── template.md        (Phase 2, + content JSON)
                                 ├── template.json
                                 ├── assets/
                                 └── previews/
```

## Setup

```bash
pip install -r requirements.txt
```

Optional, for high-fidelity layout previews instead of schematic ones:
install [LibreOffice](https://www.libreoffice.org/) and `pip install pypdfium2`.

## Usage

### Web UI (upload → review/correct → download)

On Windows, just double-click **`Start Retheme.cmd`** — it
installs dependencies on first run, starts the server, and opens your
browser. Keep its console window open while you work; closing it stops the
server. Or start it manually:

```bash
python -m pptx_template_tool.cli serve          # http://127.0.0.1:8000
```

The UI covers the full workflow:

1. **Extract a brandkit** — upload a `.pptx`/`.potx`, watch extraction
   progress, then review each layout preview next to its extracted data.
   You can correct **color roles**, **asset type classifications**
   (logo / background / decorative / icon), and **asset positions** (inches;
   % coordinates are recomputed automatically). Saving rewrites
   `template.json` *and* regenerates `template.md` from it — the two can
   never diverge. Download the package as a zip.
2. **Apply a brandkit to a content deck** — upload a presentation containing
   your content/text, and point at a brandkit: the one just extracted, an
   uploaded template-package zip, or a package folder on disk.
3. **Result** — an inline HTML preview of the branded deck, plus
   **Download PPTX**: a native PowerPoint file built on the template's own
   layouts (the package embeds the source template), fully editable in
   PowerPoint. Download HTML is also available for the HTML→PPTX pipeline.

### CLI

```bash
# Phase 1: extract a template package
python -m pptx_template_tool.cli extract template.pptx -o template-package/ [--zip]

# Phase 2: apply content to the package -> HTML deck
python -m pptx_template_tool.cli apply template-package/ content.json -o deck.html

# Restyle an existing deck: extract its text content and re-render it
# in the template package's style (one-shot); --pptx adds a native PowerPoint file
python -m pptx_template_tool.cli restyle old-deck.pptx template-package/ -o restyled.html --pptx restyled.pptx
# ... or produce/edit the intermediate content JSON yourself:
python -m pptx_template_tool.cli content old-deck.pptx -o content.json --package template-package/
```

**Restyling notes**: the PPTX export **retains all content** — each slide
is copied wholesale into the brandkit's template (retheme), so pictures
(byte-for-byte), tables, charts, shapes, icons, SmartArt and embedded
objects all survive; theme-bound colors/fonts re-resolve against the brand
theme, and chart colors matching the source theme's palette are rewritten
to the brandkit's. The HTML preview shows text, pictures and tables;
charts appear as branded markers (they are fully present in the PPTX).
If the content deck's slide size differs from the brandkit's (4:3 vs 16:9),
retained content keeps absolute positions — a warning is raised.
Use `--save-content` on `restyle` to inspect the extracted text JSON.
The `apply` command (LLM content JSON) still rebuilds slides from
placeholders — retheme only applies when the input is a deck.

### Content JSON (Phase 2 input)

See `examples/sample-content.json`. Each slide names a layout type
(`title`, `section_header`, `content`, `two_content`, `comparison`,
`title_only`, `blank`, `quote`, `agenda`, `closing`, `picture` — or an exact
layout name from the package) plus its content:

```json
{
  "title": "Deck title",
  "slides": [
    { "layout": "title", "title": "...", "subtitle": "..." },
    { "layout": "content", "title": "...", "bullets": ["...",
        { "text": "...", "children": ["sub-bullet"] }] },
    { "layout": "two_content", "title": "...", "left": ["..."], "right": ["..."] }
  ]
}
```

Slides that request a layout the template doesn't have are rendered as a
flagged "unsupported" slide and reported as a warning (never improvised).

## What the extractor captures

- **Geometry** — slide size/aspect from `presentation.xml`; all positions in
  inches *and* % of slide, so HTML placement scales at any resolution.
- **Theme** — full `clrScheme` (with the master's `clrMap` applied),
  `fontScheme` (heading/body), `fmtScheme` fill/effect presets. Semantic
  color roles (primary/secondary/accent/background/text) are inferred from
  where each color is *actually used* across masters/layouts, not from slot
  names, and are user-correctable in the review UI.
- **Layouts** — every layout (multi-master supported): inferred purpose,
  full placeholder inventory (type, position, size, z-order), per-placeholder
  text formatting resolved through the OOXML inheritance chain
  (layout ← master placeholder ← master txStyles ← theme), including bullet
  characters and indent levels, and the layout's own background
  (solid / gradient / image, including `bgRef` theme references).
- **Assets** — embedded raster images (deduplicated by content hash),
  background image fills, and decorative vector shapes converted to SVG from
  OOXML preset or custom geometry (fills, gradients, line styles, and
  `p:style` fillRef/lnRef references resolved through the theme). Each asset
  records position/size (dual units), z-order, crop/rotation/flip, owning
  layout(s), heuristic classification, and human-readable `role_notes`.
  Group transforms (`chOff`/`chExt`) are composed so grouped shapes land at
  absolute slide coordinates. Off-canvas authoring guides are skipped.
- **Grid** — margins/gutters derived as the modal placeholder edges across
  layouts, plus the title baseline when consistent.

Shapes whose geometry can't be mapped to SVG, and EMF/WMF images, are kept
with `source_format: "raster_fallback"` and flagged `needs_review` — the
review UI surfaces them with a ⚠ so a human can verify (spec §3.4/§3.6).

## Phase 2 behavior

- Fixed-pixel slide canvas (96 px/in) matching the template's aspect ratio —
  the downstream HTML→PPTX step assumes a fixed slide size.
- Elements positioned with % coordinates inside the canvas; z-order
  preserved; SVG assets inlined so they stay crisp.
- **Overflow fallback**: if content exceeds a placeholder's bounds, an inline
  script shrinks the font down to a floor of 60% of the layout's size; if it
  still overflows, the element is flagged (`data-overflow="true"` + dashed
  outline) instead of silently spilling.
- Output is one self-contained HTML file (`--linked-assets` to reference the
  package's asset folder instead of inlining).

## Resolved open decisions (spec §7)

1. **Scope** — single-template-at-a-time export (no persistent brand library).
2. **Overflow** — auto-shrink with a 60% floor, then flag; never hard-fail.
3. **Vector fallback** — common preset geometries and literal `custGeom`
   paths are converted to SVG; formula-driven custom geometry and unknown
   presets fall back (flagged placeholder SVG when no rasterizer available).
4. **Review depth** — everything is editable, but only low-confidence
   classifications and fallback formats are actively flagged ⚠.

## Portable packages (no installation, no admin)

One build command produces both flavors — `build-portable.cmd` (add
`-Only exe` or `-Only ps` to build just one). Both are fully
self-contained: copy the folder to any Windows machine and run, no Python,
no pip, no admin rights.

1. **Executable-based** — `dist\Retheme\` (~58 MB, PyInstaller).
   Run `Retheme.exe`: double-click starts the web UI in your
   browser; with arguments it is the full CLI
   (`"Retheme.exe" extract template.potx -o package\`).
   Note: the exe is unsigned — SmartScreen may warn once, and strict
   application-control policies (AppLocker) may block it.

2. **PowerShell-based** — `dist\Retheme PowerShell\` (~76 MB).
   No compiled exe at all: a signed official CPython interpreter + the app
   source + dependencies, launched by `Start Retheme.cmd` (or the
   `.ps1` directly, which also takes CLI arguments). Use this one where
   unsigned executables are blocked.

**Keep them in sync**: re-run `build-portable.cmd` after every change to
the app so the portable copies match the source.

## Fidelity audit

```bash
python -m pptx_template_tool.cli audit template.potx template-package/
```

Independently walks every visible element of every layout in the source
XML (with its own transform/visibility logic, so extractor blind spots
can't hide) and verifies the package accounts for each one at the right
position: placeholders, pictures, shapes, background masks, and static
text. Exit code 1 if anything is missing — run it after extracting a new
template to confirm nothing was dropped.

## Tests

`python -m pytest tests/` runs the regression suite. Each test builds a
synthetic template exercising one extraction nuance found on real corporate
templates — reversed gradient stops, true image backgrounds, image-filled
shapes, hidden helper shapes, zero-width/height grid lines, off-canvas
guides, `useBgFill` masks, raster-fallback exclusion from output, `.potx`
content types, and native PPTX generation — so future changes that re-break
one fail immediately.

## Project layout

```
pptx_template_tool/
├── units.py               EMU/inch/pt/% conversions
├── ooxml.py               namespaces, color resolution, transform math
├── extractor/
│   ├── extract.py         orchestrator (pptx -> package)
│   ├── theme.py           clrScheme/fontScheme/fmtScheme + role inference
│   ├── layouts.py         placeholders, formatting inheritance, backgrounds
│   ├── assets.py          image/shape/background asset collection + dedupe
│   ├── svg_convert.py     OOXML geometry -> SVG
│   ├── classify.py        asset type heuristics + role notes
│   ├── grid.py            margin/gutter/title-baseline derivation
│   ├── preview.py         LibreOffice pipeline w/ schematic fallback
│   └── package.py         template.json + template.md writer (md ⇐ json)
├── application/
│   └── generator.py       package + content JSON -> HTML deck
├── webapp/
│   ├── app.py             FastAPI: extract/review/correct/download
│   └── static/index.html  review UI
└── cli.py                 extract / apply / serve
```
