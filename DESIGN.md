---
name: Retheme
description: A local instrument for putting slide content onto a corporate template
colors:
  signal-blue: "#10069F"
  on-accent: "#ffffff"
  ink: "#1c1c28"
  muted: "#6b7280"
  line: "#e5e7eb"
  line-strong: "#7f8797"
  surface: "#fcfdff"
  bg: "#f6f7fb"
  warn: "#b45309"
  error-bg: "#fdecec"
  error-border: "#f5c2c0"
  error-text: "#b3261e"
typography:
  headline:
    fontFamily: "system-ui, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "system-ui, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.2
  data:
    fontFamily: "system-ui, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  caption:
    fontFamily: "system-ui, 'Segoe UI', sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: "4px"
  control: "5px"
  md: "8px"
  lg: "10px"
  pill: "999px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  6: "24px"
  8: "32px"
sizes:
  control: "32px"
  control-dense: "28px"
  touch-target: "44px"
  icon: "16px"
components:
  button-primary:
    backgroundColor: "{colors.signal-blue}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    height: "{sizes.control}"
    padding: "0 12px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    height: "{sizes.control}"
    padding: "0 12px"
  tab:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    height: "{sizes.control}"
    padding: "0 24px"
  tab-active:
    backgroundColor: "{colors.signal-blue}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    height: "{sizes.control}"
    padding: "0 24px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.data}"
    rounded: "{rounded.control}"
    height: "{sizes.control}"
    padding: "0 8px"
  dropzone:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.lg}"
    padding: "32px 16px"
  version-pill:
    backgroundColor: "{colors.signal-blue}"
    textColor: "{colors.on-accent}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
---

# Design System: Retheme

## 1. Overview

**Creative North Star: "The Well-Made Instrument"**

Retheme looks like a calibrated tool, not an app that wants to be admired. The
surface is a calm, cool-tinted grey with white working panels laid on top,
bordered by single hairlines. There is no gloss, no shadow, no gradient, and no
ornament that does not carry information. Everything on screen is either the
work (the rethemed slide preview) or a control that acts on it. The interface
recedes so the deck is what you look at, which is the whole point: the user came
to check a rebrand, not to enjoy a UI.

The one chromatic voice is Signal Blue (#10069F), a deep indigo that appears
only where something is actionable, active, or asking for a decision: the
primary button, the current tab, the version pill, a live-preview cue, a
drop-target on hover. Its rarity is deliberate. Against the near-neutral field,
a single blue element reads instantly as "this is where you act." Warmth is
reserved entirely for meaning: an amber warning flag, a red error panel. Color
is never spent on decoration.

This system explicitly rejects two things named in PRODUCT.md. It is not
consumer-SaaS marketing: no gradient hero, no playful illustration, no
rounded-everything, no landing-page energy. And it is not the trendy AI-app
look: no glassmorphism, no neon, no dark-with-purple glow, no animated gradient
backdrop. If a screen could be mistaken for a product's marketing page or "an AI
made this," it has failed.

**Key Characteristics:**
- Flat by default: depth is a 1px hairline plus surface contrast, never a shadow.
- One accent, used as a signal, on well under 10% of any screen.
- One system-font family carries every role; hierarchy comes from weight and color.
- Cool, blue-leaning neutrals; the only chromatic neutrals are the warn/error semantics.
- Familiar, standard controls; nothing about a common task is reinvented.

## 2. Colors

A near-neutral, cool-grey field with a single saturated accent and two reserved semantic warmths.

### Primary
- **Signal Blue** (#10069F): The only accent in the system. Fills the primary
  button, the active tab, and the version pill; tints the border and text of a
  tab on hover and a drop-zone on hover; outlines the selected layout thumbnail.
  It marks actionable, active, and live-decision surfaces, and nothing else.

### Neutral
- **Ink** (#1c1c28): Primary text and the label color on secondary buttons. A
  blue-black, never a pure black.
- **Muted** (#6b7280): Secondary and supporting text, drop-zone instructions,
  table meta, timestamps. A cool grey that leans toward the accent hue.
- **Line** (#e5e7eb): Every hairline that only divides: card borders and table
  row dividers. The workhorse of the whole system.
- **Line Strong** (#7f8797): The edge of anything you can operate: buttons,
  tabs, fields, selects and the drop-zone dash. It measures at least 3:1 against
  Surface and Background, so a control reads as a control at rest (WCAG 1.4.11).
  `tests/test_design_rules.py::test_token_contrast` holds the number.
- **Surface** (#fcfdff): The working panels (cards, tabs, inputs) that sit on
  the page field. A near-white nudged a hair toward the accent hue, so it never
  reads as clinical pure white while staying clearly lighter than Background.
- **Background** (#f6f7fb): The page field. A cool off-white, a shade bluer and
  darker than the white panels, so surfaces separate without a shadow.

### Semantic (reserved warmths, used for meaning only)
- **Warn** (#b45309): Amber. The review flag color, always paired with the warning icon
  or the word it labels, never carrying meaning by color alone.
- **Error** (bg #fdecec, border #f5c2c0, text #b3261e): The error panel. A soft
  red wash with a legible red text, used for failures and blocking warnings.

### Named Rules
**The Signal Rule.** Signal Blue is used on at most ~10% of any screen, and only
on elements that are actionable, currently active, or requesting a live
decision. It is forbidden as a background wash, a heading tint, a divider, or a
decorative flourish. Its scarcity is what makes it legible.

**The Derived-Shade Rule.** Hover, selected and soft fills are tints of the
tokens above, mixed in `tokens.css` with `color-mix()` (`--brand-hover`,
`--accent-soft`, `--hover`, `--track`). A new solid color for a state is
prohibited.

**The Tinted-Neutral Rule.** Neutrals lean cool and slightly blue (Ink, Muted,
Background). Pure warm grey is prohibited. The only non-neutral colors permitted
are the Warn amber and the Error red, and both must always be reinforced by an
icon or text label, never color alone.

## 3. Typography

**Body Font:** system-ui, with "Segoe UI" then a generic sans fallback.
**Display / Label / Mono Font:** none. The one stack does everything.

**Character:** Native and invisible. By using the operating system's own UI font,
Retheme reads as part of the machine rather than a web page. There is no
typographic personality to notice, which is the intent: the type is a clear pane
of glass over the content.

### Hierarchy
- **Headline** (700, 16px, 1.3): The app wordmark and each card's section title
  (`h1`, `h3`). Small for a heading on purpose; weight, not size, sets it apart.
- **Body** (400, 14px, 1.5): Default running text, descriptions, help copy. Prose
  blocks respect a 65–75ch measure; the app's explanatory paragraphs sit well
  inside it.
- **Label** (600, 14px, 1.2): Buttons and tab labels. Semibold is the cue that a
  string is an actionable control.
- **Data** (400, 13px, 1.4): Tables, form inputs, decision options. One step down
  from body for density where rows and fields stack.
- **Caption** (400, 12px, 1.5): The collapsible logs, layout-nav chips, and fine
  print. The version pill is a caption-scale 11px semibold.

### Named Rules
**The One Family Rule.** The system-ui stack carries headings, buttons, labels,
data, and body. A display face, a serif, or a second sans is prohibited; it
would announce the chrome and contradict the instrument.

**The Weight-Not-Size Rule.** The scale is deliberately tight (11, 12, 13, 14,
16px). Hierarchy is built from weight (400 vs 600 vs 700) and color (Ink vs
Muted), not from large size jumps. No fluid/`clamp` headings; users work at a
fixed DPI and a shrinking heading in a panel looks worse, not better.

### Spacing and sizes
- **Spacing** steps are 4, 8, 12, 16, 24 and 32px (`--sp-1` to `--sp-8`).
  Margin, padding and gap use these tokens only; a heading gets twice the room
  above it as below.
- **Controls** are 32px tall: buttons, tabs, fields and selects share the
  height, so any row of them lines up. Dense rows (table cells, layout chips)
  use 28px. On a touch screen every control reaches 44px, buttons through an
  invisible hit area and fields by growing.
- **Icons** come from one inline SVG set (16px, 2px stroke, the text color).
  No emoji and no glyph arrows.

### Named Rules
**The Spacing-Scale Rule.** `test_spacing_on_the_spacing_scale` fails on a
margin, padding or gap in `app.css` that is not a `--sp-*` token (0, 1px and
2px hairline offsets aside).

## 4. Elevation

The system is flat. There are no box-shadows anywhere. Depth is communicated
entirely by a 1px `Line` (#e5e7eb) border plus the tonal step between a white
`Surface` panel and the cooler `Background` field. A card looks lifted because
it is lighter than the page and outlined, not because it casts a shadow.

State is likewise shadow-free: a hover is a `border-color` shift to Signal Blue,
a selection is a Signal Blue edge on a soft Signal Blue tint, a disabled control
is reduced `opacity`. Nothing rises or floats.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest and flat in every state.
Elevation is a border and a background step, never a shadow or a blur. If a
component seems to need a drop shadow to read, the border or the background
contrast is too weak; fix that instead.

## 5. Components

Every component is flat, bordered, and unfussy: a hairline `Line` border, a
modest radius, no shadow, and Signal Blue reserved for the active or primary
case.

### Buttons
- **Shape:** Gently rounded (8px radius), 32px tall, 12px side padding.
- **Primary** (`class="primary"`): Signal Blue (#10069F) fill, white label,
  semibold 14px. One primary action per view, on the forward path.
- **Secondary** (the default `button`): White fill, Ink label, 1px Line Strong
  border. Same shape as primary; used for downloads and non-committal actions.
- **Hover:** secondary shifts border and label to Signal Blue; primary takes
  the `--brand-hover` tint. Only under `@media (hover: hover)`.
- **Busy:** a spinner and a changed label inside the button ("Retheme deck"
  becomes "Retheming…"), width kept, `aria-busy`, a second press ignored.
- **Disabled:** `opacity: 0.5`, `not-allowed` cursor. No color change.
- **Focus:** A 2px Signal Blue outline offset 2px, on keyboard focus
  (`:focus-visible`). The same rule covers every control.

### Tabs (signature navigation)
- **Shape:** Full pills (999px), centered in the header, 32px tall.
- **Default:** White fill, Ink label, 1px Line Strong border, semibold 14px,
  24px side padding.
- **Hover:** Border and label shift to Signal Blue (fill stays white).
- **Active:** Signal Blue fill, white label, Signal Blue border.
- **Locked:** `opacity: 0.4` with `aria-disabled` (Preview before a deck
  exists). It stays focusable so its reason can be read.
- **Keyboard:** one tab stop; arrow keys move, Home and End jump.

### Cards / Containers
- **Corner Style:** 10px radius.
- **Background:** White `Surface` on the `Background` field.
- **Shadow Strategy:** None. See Elevation; a 1px Line border plus the tonal step
  does the separating.
- **Border:** 1px solid Line (#e5e7eb).
- **Internal Padding:** 16px. Never nest a card inside a card: groups inside a
  card (the retheme choices, the protect-slides block) are rows divided by a
  hairline, not boxes.

### Inputs / Fields
- **Style:** White fill, 1px Line Strong border, 5px radius, 13px Data type,
  32px tall with 8px side padding (28px inside a table). Selects carry an SVG
  chevron.
- **Focus:** the same 2px Signal Blue outline as every other control.
- **Groups:** radios and checkboxes that answer one question sit in a
  `fieldset` with a `legend`.
- **Disabled:** Reduced opacity, consistent with buttons.

### Drop Zone (signature input)
- **Style:** A `label` over the native file input, so a click or Enter anywhere
  on it opens the picker. 2px dashed Line Strong border, 10px radius, one line
  of Muted text with an Ink `strong` cue, the accepted file types in 12px below.
- **Drag-over:** Border shifts to Signal Blue on the soft Signal Blue tint. On
  selection the file name appears in Ink below the prompt, shortened in the
  middle so the extension stays readable.
- The dashed border is the one place a 2px border is allowed, because it reads
  specifically as "drop a file here."

### Tables
- Horizontal Line rules only. Headers 12px Muted semibold; number columns and
  their headers right-aligned with tabular figures. An empty table says why in
  one spanning row. On a narrow screen the table scrolls sideways inside its
  wrapper; the page never does.

### Collapsible Logs (signature disclosure)
- A bordered `details` block (1px Line, 8px radius) with a semibold summary and a
  chevron from the icon set (right when closed, down when open, 150ms). Auto-expands when it holds a critical warning; otherwise
  starts collapsed so the deck preview stays the focus.

### Status surfaces
- **Version pill:** Signal Blue fill, white, 11px semibold, full pill. Header only.
- **Error panel:** Soft red wash (#fdecec / #f5c2c0 / #b3261e), 8px radius, for
  failures and blocking warnings. Always the warning icon, the word "Error",
  what happened and how to recover. It sits above what it concerns.
- **Review flag:** Warn amber, semibold, always the warning icon with its word.
- **Progress:** a 6px pill track with a Signal Blue fill, the step in words and
  a percentage that never reads 100% before the server confirms.

### Motion
- State changes take 150ms ease-out on color, border and background only.
  Under reduced motion color and opacity stay; movement (the button press, the
  chevron turn, the spinner's rotation) is dropped.

### Accepted deviations from the shared rules
- **Light theme only.** No dark theme (operator, 2026-11-19).
- **Pill tabs** instead of underline tabs (operator, 2026-11-19).
- **Preview frame heights** are fitted to the slide content by script, because
  the frame shows a scaled deck whose height is only known after it renders.
- **Table headers are not sticky.** The tables scroll sideways in a wrapper, and
  a sticky header would stick to that wrapper, not the page.

## 6. Do's and Don'ts

### Do:
- **Do** keep Signal Blue (#10069F) on ~10% of the screen at most: primary action,
  active tab, live-decision cue, drop-target hover. Its scarcity is the point.
- **Do** convey depth with a 1px Line (#e5e7eb) border plus the white-on-#f6f7fb
  tonal step. Flat at rest, flat in every state.
- **Do** carry every text role with the system-ui stack, and build hierarchy from
  weight (400 / 600 / 700) and color (Ink / Muted), not size.
- **Do** give every interactive control a visible focus ring, and pair every
  status color with an icon or word (the warning icon with Warn, the word with Error), so state
  never depends on color alone. The target bar is WCAG 2.1 AA.
- **Do** use standard, familiar controls: pill tabs, real `<details>`, native
  radios and file inputs. Familiarity is the feature; the tool should disappear.

### Don't:
- **Don't** ship consumer-SaaS marketing dressing: no gradient hero, no playful
  illustration, no rounded-everything, no emoji empty states, no landing-page
  energy. This is a tool, not a product page.
- **Don't** reach for the trendy AI-app look: no glassmorphism or blur cards, no
  neon, no dark-with-purple glow, no animated gradient backdrop. Nothing that
  reads as "an AI made this."
- **Don't** add box-shadows to fake elevation, or `background-clip: text`
  gradient headings, or a colored `border-left`/`border-right` stripe on cards,
  callouts, or list items. Use a full hairline border or a background tint.
- **Don't** introduce a second font family, a display face, or fluid `clamp`
  headings. One stack, fixed px scale.
- **Don't** spend Signal Blue on decoration (backgrounds, dividers, heading
  tints) or use a warm/pure-grey neutral. Neutrals lean cool; warmth is meaning.
