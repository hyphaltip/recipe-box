#!/usr/bin/env python3
"""Validate every recipe in recipes/ against the recipe-box standard.

Errors must be fixed; warnings are judgment calls. Exit code is non-zero when
any errors exist. Published recipes are held to a stricter bar than drafts.

Usage:
    python3 tools/validate.py [recipe.md ...]   # no args = all recipes
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from recipe_lib import (
    CATEGORIES,
    CUISINES,
    DIFFICULTIES,
    NUTRITION_KEYS,
    RECOMMENDED_TAGS,
    REPO_ROOT,
    REQUIRED_FIELDS,
    STATUSES,
    is_iso_date,
    is_number_or_estimate,
    load_all_recipes,
    load_recipe,
)

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
URL_RE = re.compile(r"^https?://\S+$")
LOCAL_IMAGE_RE = re.compile(r"^images/[a-z0-9]+(-[a-z0-9]+)*\.(jpg|jpeg|png|webp)$")
STEP_RE = re.compile(r"^\d+[.)]\s+\S", re.MULTILINE)
H1_RE = re.compile(r"^#\s+(.*)$", re.MULTILINE)


def validate_one(recipe: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one loaded recipe."""
    meta, body, slug, path = recipe["meta"], recipe["body"], recipe["slug"], recipe["path"]
    errors: list[str] = []
    warnings: list[str] = []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    # --- required fields -----------------------------------------------------
    for field in REQUIRED_FIELDS:
        if meta.get(field) is None or meta.get(field) == "":
            err(f"missing required frontmatter field: {field}")

    if errors:
        return errors, warnings  # nothing more is safe to check

    # --- enums ---------------------------------------------------------------
    if meta["category"] not in CATEGORIES:
        err(f"category '{meta['category']}' not in {CATEGORIES}")
    if meta["difficulty"] not in DIFFICULTIES:
        err(f"difficulty '{meta['difficulty']}' not in {DIFFICULTIES}")
    if meta["status"] not in STATUSES:
        err(f"status '{meta['status']}' not in {STATUSES}")

    # --- id / filename -------------------------------------------------------
    if not SLUG_RE.fullmatch(slug):
        err(f"filename '{path.name}' is not a valid slug (lowercase, hyphens)")
    if meta["id"] != slug:
        err(f"id '{meta['id']}' does not match filename stem '{slug}'")
    if len(slug) > 64:
        err(f"slug longer than 64 characters: {len(slug)}")

    # --- scalars -------------------------------------------------------------
    title = meta["title"]
    if not isinstance(title, str) or len(title) < 3:
        err("title must be a string of at least 3 characters")
    elif len(title) > 120:
        warn("title longer than 120 characters")

    cuisine = meta["cuisine"]
    if not isinstance(cuisine, str) or not SLUG_RE.fullmatch(cuisine):
        err(f"cuisine '{cuisine}' must be lowercase-hyphen")
    elif cuisine not in CUISINES:
        warn(f"cuisine '{cuisine}' not in the controlled vocabulary "
             f"(add it to docs/data-model.md if it should be)")

    for field in ("servings", "prep_time", "cook_time"):
        value = meta[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            err(f"{field} must be a non-negative integer, got {value!r}")
    if isinstance(meta.get("servings"), int) and meta["servings"] < 1:
        err("servings must be >= 1")

    # --- tags ------------------------------------------------------------------
    tags = meta["tags"]
    if not isinstance(tags, list) or not tags:
        err("tags must be a non-empty list")
    else:
        for tag in tags:
            if not isinstance(tag, str) or not SLUG_RE.fullmatch(tag):
                err(f"invalid tag: {tag!r}")
            elif tag not in RECOMMENDED_TAGS:
                warn(f"tag '{tag}' not in the recommended vocabulary")
        duplicates = [t for t, n in Counter(tags).items() if n > 1]
        if duplicates:
            err(f"duplicate tags: {duplicates}")
        if "quick" in tags and isinstance(meta["prep_time"], int) and isinstance(meta["cook_time"], int):
            if meta["prep_time"] + meta["cook_time"] > 30:
                err("tag 'quick' requires prep + cook <= 30 minutes")

    # --- dates -----------------------------------------------------------------
    for field in ("created", "updated"):
        if not is_iso_date(meta[field]):
            err(f"{field} must be an ISO date (YYYY-MM-DD), got {meta[field]!r}")
    if is_iso_date(meta["created"]) and is_iso_date(meta["updated"]):
        if meta["updated"] < meta["created"]:
            err("updated date is before created date")

    # --- source ------------------------------------------------------------------
    source = meta["source"]
    if not isinstance(source, dict) or not str(source.get("name", "")).strip():
        err("source must be a mapping with a non-empty 'name'")
    else:
        url = source.get("url")
        if url not in (None, "") and not URL_RE.match(str(url)):
            err(f"source.url is not a valid URL: {url!r}")

    # --- image -------------------------------------------------------------------
    image = meta.get("image")
    if image not in (None, ""):
        image = str(image)
        if URL_RE.match(image):
            pass
        elif LOCAL_IMAGE_RE.match(image):
            if not (REPO_ROOT / image).is_file():
                err(f"image file not found: {image} (place it at repo root under images/)")
        else:
            err(
                f"image must be an http(s) URL or a local 'images/<slug>.<ext>' "
                f"path (jpg/jpeg/png/webp), got {image!r}"
            )

    # --- nutrition -----------------------------------------------------------------
    nutrition = meta.get("nutrition")
    if nutrition not in (None, {}):
        if not isinstance(nutrition, dict):
            err("nutrition must be a mapping")
        else:
            for key, value in nutrition.items():
                if key not in NUTRITION_KEYS:
                    warn(f"nutrition key '{key}' is non-standard")
                elif not is_number_or_estimate(value):
                    err(f"nutrition.{key} must be a number or '~123' string, got {value!r}")
    elif meta["status"] == "published":
        warn("published recipe has no nutrition block")

    # --- body -------------------------------------------------------------------------
    if not re.search(r"^##\s+Ingredients\s*$", body, re.MULTILINE):
        err("body is missing an '## Ingredients' section")
    if not re.search(r"^##\s+Instructions\s*$", body, re.MULTILINE):
        err("body is missing an '## Instructions' section")

    def section(text: str, heading: str) -> str:
        match = re.search(rf"^##\s+{heading}\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
        return match.group(1) if match else ""

    ingredients_section = section(body, "Ingredients")
    bullet_count = len(re.findall(r"^[-*]\s+\S", ingredients_section, re.MULTILINE))
    if bullet_count == 0:
        err("Ingredients section has no bullet items")
    elif bullet_count < 3:
        warn(f"only {bullet_count} ingredient(s) — double-check the recipe is complete")
    if "TODO" in ingredients_section:
        err("Ingredients section still contains TODO placeholders")

    instructions_section = section(body, "Instructions")
    step_count = len(re.findall(STEP_RE, instructions_section))
    if step_count == 0:
        err("Instructions section has no numbered steps")
    if "TODO" in instructions_section:
        err("Instructions section still contains TODO placeholders")

    if not re.search(r"^##\s+Notes\s*&\s+Substitutions\s*$", body, re.MULTILINE):
        warn("body is missing a '## Notes & Substitutions' section (health-audit)")
    if not re.search(r"^##\s+Storage\s*&\s+Make-Ahead\s*$", body, re.MULTILINE):
        warn("body is missing a '## Storage & Make-Ahead' section")

    h1 = re.search(H1_RE, body)
    if not h1:
        err("body is missing an H1 title")
    elif isinstance(title, str) and h1.group(1).strip() != title.strip():
        warn("H1 title does not match frontmatter title")

    if meta["status"] == "published":
        for marker in re.findall(r"<!--.*?draft.*?-->", body, re.DOTALL | re.IGNORECASE):
            warn("published recipe still contains a draft-note comment")
        if "TODO" in body:
            err("published recipe still contains TODO placeholders")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recipes", nargs="*", help="specific recipe files (default: all)")
    parser.add_argument("--quiet", action="store_true", help="only print failures and the summary")
    args = parser.parse_args()

    if args.recipes:
        recipes, failures = [], []
        for raw in args.recipes:
            path = Path(raw)
            try:
                recipes.append(load_recipe(path))
            except ValueError as exc:
                failures.append({"path": path, "error": str(exc)})
    else:
        recipes, failures = load_all_recipes(verbose=False)

    if not recipes and not failures:
        print("No recipes found in recipes/ — nothing to validate.")
        return 0

    error_count = warn_count = 0
    ok_count = 0
    for recipe in recipes:
        errors, warnings = validate_one(recipe)
        name = recipe["path"].name
        if errors:
            error_count += len(errors)
            print(f"FAIL  {name}")
            for message in errors:
                print(f"      error:   {message}")
        elif warnings:
            print(f"WARN  {name}")
        else:
            ok_count += 1
            if not args.quiet:
                print(f"OK    {name}")
        for message in warnings:
            print(f"      warning: {message}")
        warn_count += len(warnings)

    for failure in failures:
        error_count += 1
        print(f"FAIL  {failure['path'].name}")
        print(f"      error:   {failure['error']}")

    total = len(recipes) + len(failures)
    print(f"\n{total} recipe(s): {ok_count} ok, "
          f"{warn_count} warning(s), {error_count} error(s)")
    if error_count:
        print("Fix the errors above before committing (see AGENT.md).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
