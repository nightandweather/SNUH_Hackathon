"""Check canonical CSS reuse and nested-SVG regressions without a browser.

Run after build_private_shared_shell.py. This only reads presentation assets;
it does not load patient records, start a server, or rebuild the application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def rules(css: str):
    """Read leaf declaration blocks, including those inside media queries."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [re.sub(r"\s+", " ", s.strip())
                     for s in match[1].split(",")]
        declarations = dict((key.strip().lower(), value.strip())
                            for key, value in re.findall(
                                r"([\w-]+)\s*:\s*([^;]+)", match[2]))
        yield selectors, declarations


def validate(root: Path, public: Path) -> dict:
    static = root / "static"
    source = (public / "index.html").read_text()
    expected_css = "\n".join(re.findall(r"<style>(.*?)</style>", source, re.S))
    expected_css += "\n" + (public / "static/app-shell.css").read_text()
    copied_css = (static / "shared-presentation.css").read_text()
    adapter_css = (static / "shared-clinical.css").read_text()
    controller = (static / "shared-clinical-controller.js").read_text()
    metadata = json.loads((static / "shared-shell-version.json").read_text())
    all_rules = list(rules(copied_css + "\n" + adapter_css))
    checks = {}
    checks["canonical_css_matches"] = digest(copied_css) == digest(expected_css)
    checks["canonical_source_hash_matches"] = metadata.get("source_sha256") == digest(source)

    # A descendant selector also reaches the tiny SVGs inside each bed icon.
    sizing = {"width", "height", "min-width", "min-height", "max-width", "max-height"}
    unsafe = [selector for selectors, props in all_rules if sizing.intersection(props)
              for selector in selectors if re.search(r"#floors\s+svg\b", selector)]
    checks["outer_map_sizing_is_scoped"] = not unsafe

    # CSS overrides SVG width/height presentation attributes. Card icons need
    # their own scoped dimensions when rendered outside .bed-care-icons.
    if re.search(r'class="[^"]*\bcard-care\b', controller):
        icon_dimensions = {}
        for selectors, props in all_rules:
            if any(re.fullmatch(r"\.card-care\s+(?:>\s*)?svg", s) for s in selectors):
                icon_dimensions.update({k: v for k, v in props.items() if k in sizing})
        checks["card_nested_svg_dimensions_preserved"] = (
            icon_dimensions.get("width") == ".76px"
            and icon_dimensions.get("height") == ".48px"
            and icon_dimensions.get("min-width", "0") in ("0", "0px", "auto")
        )
    else:
        # The canonical HTML card pictograms avoid nested map SVGs entirely.
        # Verify their renderer is used and available in the private export.
        icons = (static / "shared-care-icons.js").read_text()
        exports = icons.rsplit("return {", 1)[-1]
        checks["card_nested_svg_dimensions_preserved"] = all(
            "Network." + name in controller and name in exports
            for name in ("careStrip", "bedDrawing"))

    occupied_cards = [tag for tag in re.findall(r"<(?:button|article)\b[^>]*>", controller)
                      if re.search(r'class="[^"]*\bpatient-card\b', tag)
                      and "data-case=" in tag]
    checks["occupied_card_color_token_present"] = bool(occupied_cards) and all(
        "--bed-color:" in tag for tag in occupied_cards)
    return {"ok": all(checks.values()), "checks": checks,
            "canonical_css_sha256": digest(expected_css),
            "built_css_sha256": digest(copied_css), "unsafe_svg_selectors": unsafe}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--public", type=Path)
    args = parser.parse_args()
    result = validate(args.root, args.public or args.root.parent / "public-icu-preview/dist")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
