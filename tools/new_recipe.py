#!/usr/bin/env python3
"""Scaffold a new recipe file in the standard format.

Examples:
    python3 tools/new_recipe.py "Shakshuka" --cuisine middle-eastern --category breakfast
    python3 tools/new_recipe.py "Chana Masala" --cuisine indian --tags "healthy,vegan,budget"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from recipe_lib import (
    CATEGORIES,
    DIFFICULTIES,
    RECIPES_DIR,
    TEMPLATE_PATH,
    slugify,
    today,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title", help="recipe title, e.g. \"Sheet-Pan Miso Salmon\"")
    parser.add_argument("--cuisine", default="other", help="controlled cuisine (default: other)")
    parser.add_argument("--category", default="dinner", choices=CATEGORIES)
    parser.add_argument("--servings", type=int, default=4)
    parser.add_argument("--prep-time", type=int, default=15, help="minutes")
    parser.add_argument("--cook-time", type=int, default=30, help="minutes")
    parser.add_argument("--difficulty", default="easy", choices=DIFFICULTIES)
    parser.add_argument("--tags", default="healthy", help="comma-separated tags")
    parser.add_argument("--source-name", default="Original creation")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-author", default="")
    parser.add_argument("--image", default="", help="photo URL (optional)")
    parser.add_argument("--status", default="draft", choices=["draft", "published"])
    parser.add_argument("--force", action="store_true", help="overwrite existing file")
    parser.add_argument("--stdout", action="store_true", help="print to stdout instead of writing")
    return parser.parse_args()


def render_template(values: dict) -> str:
    """Fill templates/recipe-template.md placeholders; drop lines for empty optional values."""
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    # Remove whole lines that reference a placeholder whose value is empty
    for key, value in values.items():
        if value in ("", None):
            placeholder = re.escape("{{" + key + "}}")
            text = re.sub(rf"^[ \t]*[^\n]*{placeholder}[ \t]*\n", "", text, flags=re.MULTILINE)
    # Drop block keys whose children were all removed (e.g. a fully empty nutrition block)
    text = re.sub(r"^[A-Za-z_-]+:\n(?=\S)", "", text, flags=re.MULTILINE)
    # Substitute remaining placeholders
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    # Collapse runs of blank lines created by dropped lines (keep max one)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    args = parse_args()

    if args.servings < 1:
        parser_error("--servings must be >= 1")

    slug = slugify(args.title)
    if not slug:
        parser_error("title produces an empty slug — use a title with letters/numbers")

    tags = ", ".join(t.strip() for t in args.tags.split(",") if t.strip())
    values = {
        "id": slug,
        "title": args.title,
        "cuisine": args.cuisine,
        "category": args.category,
        "servings": args.servings,
        "prep_time": args.prep_time,
        "cook_time": args.cook_time,
        "difficulty": args.difficulty,
        "tags": f"[{tags}]",
        "status": args.status,
        "source_name": args.source_name,
        "source_url": args.source_url,
        "source_author": args.source_author,
        "source_license": "CC-BY-4.0" if args.source_name == "Original creation" else "",
        "calories": "",
        "protein_g": "",
        "carbs_g": "",
        "fat_g": "",
        "created": today(),
        "updated": today(),
    }
    content = render_template(values)

    if args.image:
        content = content.replace("status: ", f"image: {args.image}\nstatus: ", 1)

    if args.stdout:
        print(content, end="")
        return 0

    out_path = RECIPES_DIR / f"{slug}.md"
    if out_path.exists() and not args.force:
        print(f"error: {out_path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1

    out_path.write_text(content, encoding="utf-8")
    print(f"Created {out_path}")
    print("\nNext steps:")
    print(f"  1. Edit the file:      $EDITOR {out_path}")
    print("  2. Fill ingredients & instructions; run the health-audit (see AGENT.md)")
    print("  3. Set status: published when ready")
    print("  4. python3 tools/validate.py && python3 tools/catalog.py")
    print(f"  5. git add recipes/ && git commit -m 'recipe: add {slug}'")
    return 0


def parser_error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    sys.exit(main())
