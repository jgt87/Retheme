"""PPTX template extraction & application tool.

Phase 1 (extractor): .pptx/.potx -> template package (template.md,
template.json, assets/, previews/).
Phase 2 (application): template package + slide-content JSON -> HTML deck.
"""

# Bump when extraction output changes so stale packages can be detected:
# applying a package stamped with an older version produces a warning
# telling the user to re-extract.
__version__ = "0.3.0"
