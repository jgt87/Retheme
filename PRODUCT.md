# Product

## Register

product

## Users

The author (JGT) and a small number of colleagues. This is a personal and
small-team internal utility, not a distributed product. Usage is occasional
and task-driven: someone has a PowerPoint content deck and a corporate
template, and needs the deck to match the template. They run Retheme locally
on Windows (double-click launcher, opens in the browser at localhost), do the
job, and close it.

The job to be done, in two flows:
1. Extract a reusable "brandkit" from a corporate PowerPoint template.
2. Retheme a content deck with that brandkit, review the result, and download
   a natively-editable PPTX (or HTML preview).

Users are comfortable with PowerPoint and corporate decks. They are not
looking to learn a new app; they want the rebrand done correctly with minimal
fiddling.

## Product Purpose

Retheme takes the tedium and inconsistency out of putting existing slide
content onto a corporate template. It extracts a template's theme, layouts,
colors, fonts and assets into a portable brandkit, then transplants a content
deck onto that brandkit while retaining everything (text, pictures, tables,
charts, shapes, SmartArt) and re-resolving styling against the brand theme.

Success looks like: a correctly rebranded, fully editable deck produced in a
couple of minutes, with the user confident that nothing was lost, nothing was
silently changed, and the output opens cleanly in PowerPoint. The tool exists
because doing this by hand is slow and error-prone, and because consistency
across decks matters more than any single slide.

## Brand Personality

Efficient, precise, quiet. The interface behaves like a well-made instrument:
it does exactly what it says, shows its work, and stays out of the way.

Voice and tone: plain, direct, technically literal. Microcopy states facts and
consequences without hype or filler ("this package was extracted with an older
version, re-extract to refresh"). No marketing language, no cheerleading, no
personality flourishes. When something is retained, converted, or skipped, the
tool says so in the user's terms.

Emotional goal: confidence. The user should trust that the rebrand is faithful
and complete, and never wonder what the tool did behind their back.

## Anti-references

- **Consumer SaaS marketing.** No gradient hero sections, playful
  illustrations, rounded-everything, emoji-driven empty states, or
  landing-page energy. This is a tool, not a product page.
- **Trendy AI-app look.** No glassmorphism, neon accents, dark-with-purple
  glow, or animated gradient backdrops. Nothing that reads as "an AI made
  this."
- More broadly: nothing decorative that slows the core workflow, and nothing
  that draws attention to the chrome instead of the deck.

## Design Principles

1. **The deck is the hero.** The rethemed slide preview is what the user came
   to see. The surrounding UI should recede so the output, not the interface,
   holds attention.
2. **Correctness is the product.** Fidelity to the source content and the
   brand template matters more than any visual flourish. Every state, including
   errors, edge cases, size mismatches and outdated packages, is handled
   honestly rather than hidden.
3. **Trust through transparency.** Show the work. Let the user review before
   committing (color roles, asset types, positions), surface what was retained,
   converted or skipped, and never mutate content silently. Logs and warnings
   are a feature, not clutter.
4. **Fast path, no ceremony.** The common task (upload, retheme, download)
   should be a few clicks with no modal gauntlet and no forced wizard. Guidance
   appears where a decision is genuinely needed, and defaults are sensible.
5. **Quiet by default, loud only when it matters.** A calm, neutral surface;
   emphasis and color are reserved for the brand accent, live decisions, and
   genuine warnings, so the signals that need attention actually get it.

## Accessibility & Inclusion

Target WCAG 2.1 AA.

- Text contrast at least 4.5:1 (3:1 for large text and meaningful UI
  boundaries); never rely on color alone to convey state (pair the warning
  color with an icon or label, as the review flags already do).
- Full keyboard operability: the tab navigation, radio groups, file
  drop zones, collapsible logs, and all controls reachable and operable by
  keyboard, with a visible focus indicator on every interactive element.
- Correct semantics and labels: the tab bar exposed as tabs, form controls
  associated with their labels, the collapsible logs using a real disclosure
  control, and iframes titled.
- Respect `prefers-reduced-motion`: keep the few transitions subtle and
  disable non-essential motion when the user asks for less.
