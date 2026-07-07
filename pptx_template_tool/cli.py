"""Command-line interface.

  python -m pptx_template_tool.cli extract template.pptx -o template-package/
  python -m pptx_template_tool.cli apply template-package/ content.json -o deck.html
  python -m pptx_template_tool.cli serve [--port 8000]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_extract(args) -> int:
    from .extractor.extract import extract_template
    from .extractor.package import zip_package

    def progress(step, frac):
        print(f"  [{frac * 100:3.0f}%] {step}")

    manifest = extract_template(args.pptx, args.out, progress=progress)
    print(f"\nPackage written to {args.out}")
    print(f"  layouts: {len(manifest['layouts'])}, assets: {len(manifest['assets'])}, "
          f"previews: {manifest.get('preview_mode')}")
    flagged = [a["asset_id"] for a in manifest["assets"] if a.get("needs_review")]
    if flagged:
        print(f"  [!] needs review: {', '.join(flagged[:8])}"
              + (f" (+{len(flagged) - 8})" if len(flagged) > 8 else ""))
    if args.zip:
        zip_path = Path(args.out).with_suffix(".zip")
        zip_package(Path(args.out), zip_path)
        print(f"  zipped: {zip_path}")
    return 0


def cmd_apply(args) -> int:
    from .application.generator import generate_file
    warnings = generate_file(args.package, args.content, args.out,
                             inline_assets=not args.linked_assets)
    print(f"Wrote {args.out}")
    if args.pptx:
        from .application.pptx_generator import generate_pptx_file
        warnings += generate_pptx_file(args.package, args.content, args.pptx)
        print(f"Wrote {args.pptx}")
    for w in warnings:
        print(f"  [!] {w}")
    return 0


def cmd_content(args) -> int:
    from .application.content_extract import extract_content_file
    warnings = extract_content_file(args.pptx, args.out, args.package)
    print(f"Wrote {args.out}")
    for w in warnings:
        print(f"  [!] {w}")
    return 0


def cmd_restyle(args) -> int:
    """Deck + template package -> HTML deck in the template's style."""
    import json
    from .application.content_extract import extract_content
    from .application.generator import generate_html
    from pathlib import Path as P

    import tempfile

    content, warnings = extract_content(args.pptx, args.package)
    gen_warnings: list[str] = []
    # retheme retains ALL deck content at original positions, and the HTML
    # preview is rendered from the rethemed file so both always match;
    # rebuild-from-text is only a fallback for old packages
    try:
        from .application.preview_render import render_deck_html
        from .application.retheme import retheme_pptx
        pptx_out = args.pptx_out or str(
            P(tempfile.mkdtemp(prefix="retheme-")) / "branded.pptx")
        gen_warnings += retheme_pptx(args.package, args.pptx, pptx_out)
        doc, pv_warnings = render_deck_html(args.package, pptx_out,
                                            P(args.pptx).stem)
        gen_warnings += pv_warnings
        if args.pptx_out:
            print(f"Wrote {args.pptx_out}")
    except FileNotFoundError:
        doc, html_warnings = generate_html(args.package, content,
                                           inline_assets=not args.linked_assets)
        gen_warnings += html_warnings
        if args.pptx_out:
            from .application.pptx_generator import generate_pptx
            gen_warnings += generate_pptx(args.package, content, args.pptx_out)
            print(f"Wrote {args.pptx_out}")
    P(args.out).write_text(doc, encoding="utf-8")
    if args.save_content:
        P(args.save_content).write_text(
            json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {args.save_content}")
    print(f"Wrote {args.out} ({len(content['slides'])} slides)")
    for w in warnings + gen_warnings:
        print(f"  [!] {w}")
    return 0


def cmd_audit(args) -> int:
    from .extractor.audit import audit_package, print_report
    report = audit_package(args.pptx, args.package)
    print_report(report)
    return 0 if report["total_missing"] == 0 else 1


def cmd_serve(args) -> int:
    import uvicorn
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("=" * 70)
        print(f"WARNING: binding to {args.host} exposes this tool to the "
              f"network WITHOUT any authentication.")
        print("Anyone who can reach this machine can upload files, read "
              "extracted packages, and point the apply flow at folders on "
              "this computer. Only do this on a trusted network.")
        print("=" * 70)
    uvicorn.run("pptx_template_tool.webapp.app:app",
                host=args.host, port=args.port)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="retheme")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="pptx/potx -> template package")
    p.add_argument("pptx")
    p.add_argument("-o", "--out", default="template-package")
    p.add_argument("--zip", action="store_true", help="also write a .zip")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("apply", help="template package + content JSON -> HTML deck")
    p.add_argument("package")
    p.add_argument("content")
    p.add_argument("-o", "--out", default="deck.html")
    p.add_argument("--pptx", default=None, metavar="PPTX",
                   help="also generate a native .pptx")
    p.add_argument("--linked-assets", action="store_true",
                   help="reference asset files instead of inlining them")
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("content", help="existing deck -> content JSON")
    p.add_argument("pptx")
    p.add_argument("-o", "--out", default="content.json")
    p.add_argument("--package", default=None,
                   help="template package dir: keeps exact layout names "
                        "that exist in the package")
    p.set_defaults(fn=cmd_content)

    p = sub.add_parser("restyle",
                       help="existing deck + template package -> styled HTML")
    p.add_argument("pptx")
    p.add_argument("package")
    p.add_argument("-o", "--out", default="restyled-deck.html")
    p.add_argument("--pptx", dest="pptx_out", default=None, metavar="PPTX",
                   help="also generate a native .pptx")
    p.add_argument("--save-content", default=None, metavar="JSON",
                   help="also write the intermediate content JSON for editing")
    p.add_argument("--linked-assets", action="store_true",
                   help="reference asset files instead of inlining them")
    p.set_defaults(fn=cmd_restyle)

    p = sub.add_parser("audit",
                       help="verify a package captures every visible "
                            "element of the source template")
    p.add_argument("pptx")
    p.add_argument("package")
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser("serve", help="run the upload/review web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_serve)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
