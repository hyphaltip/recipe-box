#!/usr/bin/env python3
"""Import one or more recipes from structured JSON into the recipe-box format.

This is the low-friction path for another agent (or any script) to push
recipes into the database without producing exact Markdown by hand — it only
has to emit JSON in the shape below, and this tool renders a valid,
schema-conformant recipe file, the same as a human editing the template
would. See docs/import-format.md for the full field reference.

Usage:
    python3 tools/import_recipe.py recipe.json              # one recipe
    python3 tools/import_recipe.py batch.json                # JSON array of recipes
    python3 tools/import_recipe.py --dir incoming/            # every *.json in a dir
    python3 tools/import_recipe.py recipe.json --dry-run       # preview, write nothing
    python3 tools/import_recipe.py recipe.json --publish       # force status: published
    cat recipe.json | python3 tools/import_recipe.py -         # read from stdin

Minimal JSON object:
    {
      "title": "Sheet-Pan Miso Salmon",
      "cuisine": "japanese", "category": "dinner",
      "servings": 4, "prep_time": 10, "cook_time": 20,
      "difficulty": "easy", "tags": ["healthy", "quick", "one-pan"],
      "source": {"name": "Original creation"},
      "hook": "A one-pan dinner ready in half an hour.",
      "ingredients": ["4 salmon fillets, skin on", "..."],
      "instructions": ["Preheat the oven to 425F (220C).", "..."],
      "notes": ["Swap salmon for tofu for a vegan version."],
      "storage": ["Keeps 2 days refrigerated in an airtight container."]
    }

Omitted optional fields fall back to the same defaults as
tools/new_recipe.py (difficulty: medium, status: draft, tags: [healthy]).
Each written recipe is validated immediately afterward (tools/validate.py)
and results are printed; the process exits non-zero if any recipe fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from recipe_lib import (
    RECIPES_DIR,
    load_all_recipes,
    normalize_title,
    render_markdown,
    slugify,
    today,
)
from validate import validate_one

REQUIRED_LIST_FIELDS = ["ingredients", "instructions"]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def build_existing_index() -> tuple[dict[str, set], dict[str, set]]:
    """Index recipes already in recipes/ by normalized title and by source URL.

    Returns (by_title, by_url), each mapping a key to a set of existing slugs.
    """
    by_title: dict[str, set] = defaultdict(set)
    by_url: dict[str, set] = defaultdict(set)
    for recipe in load_all_recipes(verbose=False)[0]:
        title = normalize_title(str(recipe["meta"].get("title") or ""))
        if title:
            by_title[title].add(recipe["slug"])
        url = str((recipe["meta"].get("source") or {}).get("url") or "").strip()
        if url:
            by_url[url].add(recipe["slug"])
    return by_title, by_url


def find_duplicate(
    record: dict,
    existing_by_title: dict[str, set],
    existing_by_url: dict[str, set],
    seen_title: dict[str, set],
    seen_url: dict[str, set],
) -> str | None:
    """Return the slug of an existing recipe this record duplicates, or None.

    Matches on normalized title first (catches the same recipe re-captured with a
    fresh slug, e.g. 'peanut-butter-and-jelly-sandwich-2'), then on source URL
    (catches a re-capture whose title was slightly adapted). Records already
    imported earlier in this same run are also considered via the `seen_*` maps.
    """
    title = normalize_title(str(record.get("title") or ""))
    if title:
        match = existing_by_title.get(title) or seen_title.get(title)
        if match:
            return min(match)
    url = str((record.get("source") or {}).get("url") or "").strip()
    if url:
        match = existing_by_url.get(url) or seen_url.get(url)
        if match:
            return min(match)
    return None


def load_records(sources: list[str], use_dir: Path | None) -> list[tuple[str, dict]]:
    """Return [(label, record), ...] from files/stdin/dir, expanding JSON arrays."""
    records: list[tuple[str, dict]] = []

    def add_from_text(label: str, text: str) -> None:
        data = json.loads(text)
        items = data if isinstance(data, list) else [data]
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                sys.exit(f"error: {label}[{i}] is not a JSON object")
            item_label = f"{label}[{i}]" if len(items) > 1 else label
            records.append((item_label, item))

    if use_dir is not None:
        files = sorted(use_dir.glob("*.json"))
        if not files:
            sys.exit(f"error: no *.json files found in {use_dir}")
        for path in files:
            add_from_text(path.name, path.read_text(encoding="utf-8"))

    for source in sources:
        if source == "-":
            add_from_text("<stdin>", sys.stdin.read())
        else:
            path = Path(source)
            if not path.is_file():
                sys.exit(f"error: {source} is not a file")
            add_from_text(path.name, path.read_text(encoding="utf-8"))

    return records


def build_recipe(record: dict, label: str, force_publish: bool) -> tuple[str, dict, str]:
    """Turn one JSON record into (slug, meta, body). Exits on hard structural errors."""
    title = str(record.get("title") or "").strip()
    if not title:
        sys.exit(f"error: {label}: missing required field 'title'")

    for field in REQUIRED_LIST_FIELDS:
        value = record.get(field)
        if not isinstance(value, list) or not value:
            sys.exit(f"error: {label}: '{field}' must be a non-empty list of strings")

    slug = slugify(str(record.get("id") or record.get("slug") or title))
    if not slug:
        sys.exit(f"error: {label}: title produces an empty slug")

    source = record.get("source") or {"name": "Original creation"}
    if not isinstance(source, dict) or not str(source.get("name", "")).strip():
        source = {"name": "Original creation"}

    status = "published" if force_publish else str(record.get("status") or "draft")

    meta = {
        "id": slug,
        "title": title,
        "cuisine": str(record.get("cuisine") or "other"),
        "category": str(record.get("category") or "dinner"),
        "servings": int(record.get("servings") or 4),
        "prep_time": int(record.get("prep_time") or 15),
        "cook_time": int(record.get("cook_time") or 30),
        "difficulty": str(record.get("difficulty") or "medium"),
        "tags": list(record.get("tags") or ["healthy"]),
        "status": status,
        "source": source,
        "created": str(record.get("created") or today()),
        "updated": str(record.get("updated") or today()),
    }
    if record.get("image"):
        meta["image"] = str(record["image"])
    if record.get("nutrition"):
        meta["nutrition"] = record["nutrition"]

    hook = str(record.get("hook") or "").strip() or "TODO: one-sentence hook."
    body_lines = [f"# {title}", "", f"> {hook}", "", "## Ingredients", ""]
    body_lines += [f"- {str(item).strip()}" for item in record["ingredients"]]
    body_lines += ["", "## Instructions", ""]
    body_lines += [f"{i}. {str(step).strip()}" for i, step in enumerate(record["instructions"], 1)]
    body_lines += ["", "## Notes & Substitutions", ""]
    body_lines += [f"- {str(n).strip()}" for n in record.get("notes") or []]
    body_lines += ["", "## Storage & Make-Ahead", ""]
    body_lines += [f"- {str(s).strip()}" for s in record.get("storage") or []]
    body_lines.append("")

    return slug, meta, "\n".join(body_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help="JSON file(s), or '-' for stdin")
    parser.add_argument("--dir", type=Path, help="import every *.json file in this directory")
    parser.add_argument("--output-dir", type=Path, default=RECIPES_DIR)
    parser.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    parser.add_argument("--publish", action="store_true", help="force status: published on every imported recipe")
    parser.add_argument("--force", action="store_true", help="overwrite existing recipe files")
    args = parser.parse_args()

    if not args.sources and not args.dir:
        parser.error("give at least one JSON file, '-' for stdin, or --dir")

    records = load_records(args.sources, args.dir)
    had_error = False
    imported = 0
    skipped = 0
    duplicated = 0

    existing_by_title, existing_by_url = build_existing_index()
    seen_title: dict[str, set] = defaultdict(set)
    seen_url: dict[str, set] = defaultdict(set)

    for label, record in records:
        slug, meta, body = build_recipe(record, label, args.publish)
        out_path = args.output_dir / f"{slug}.md"

        # Deduplicate against recipes already in the repo (and this run). The
        # import bot re-captures the same recipe with a new slug, which would
        # otherwise silently create a second copy. `--force` skips this so an
        # intentional update via a matching slug/title still lands.
        if not args.force:
            dup_slug = find_duplicate(
                record, existing_by_title, existing_by_url, seen_title, seen_url
            )
            if dup_slug:
                print(f"DUPLICATE  {label} -> matches existing '{dup_slug}' "
                      f"(incoming id '{slug}'); skipping")
                duplicated += 1
                continue
            title = normalize_title(str(record.get("title") or ""))
            if title:
                seen_title[title].add(slug)
            url = str((record.get("source") or {}).get("url") or "").strip()
            if url:
                seen_url[url].add(slug)

        if out_path.exists() and not args.force and not args.dry_run:
            print(f"SKIP  {label} -> {out_path.name} (already exists; use --force to overwrite)")
            had_error = True
            skipped += 1
            continue

        content = render_markdown(meta, body)

        if args.dry_run:
            print(f"--- {label} -> {out_path.name} (dry run) ---")
            print(content)
            continue

        out_path.write_text(content, encoding="utf-8")
        imported += 1

        loaded = {"slug": slug, "path": out_path, "meta": meta, "body": body}
        errors, warnings = validate_one(loaded)
        status_word = "FAIL" if errors else ("WARN" if warnings else "OK")
        print(f"{status_word}  {label} -> {out_path.name}")
        for message in errors:
            print(f"      error:   {message}")
            had_error = True
        for message in warnings:
            print(f"      warning: {message}")

    if not args.dry_run and records:
        print(f"\n{imported} recipe(s) imported into {args.output_dir}"
              f" ({duplicated} duplicate(s) skipped, {skipped} skip(s) due to an existing file)")
        print("Next: python3 tools/validate.py && python3 tools/catalog.py && python3 tools/build_site.py")

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
