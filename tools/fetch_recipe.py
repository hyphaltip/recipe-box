#!/usr/bin/env python3
"""Capture a recipe from a URL or a saved HTML page into a draft recipe file.

Most recipe websites embed a schema.org Recipe object in JSON-LD
(<script type="application/ld+json">). This tool extracts it and renders a
draft recipe file in the recipe-box standard. Drafts always start as
`status: draft` — the agent then standardizes and health-audits them
(see AGENT.md) before publishing.

Usage:
    python3 tools/fetch_recipe.py https://www.sitename.com/recipe/page
    python3 tools/fetch_recipe.py saved-page.html --slug my-recipe

If a site blocks the fetch, save the page manually
(e.g. `curl -A 'Mozilla/5.0' -o page.html <url>`) and pass the file path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from recipe_lib import RECIPES_DIR, iso_duration_to_minutes, render_markdown, slugify, today

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

CATEGORY_MAP = {
    "breakfast": "breakfast", "brunch": "breakfast",
    "lunch": "lunch", "lunches": "lunch",
    "dinner": "dinner", "dinner-main": "dinner", "main course": "dinner",
    "main": "dinner", "main dish": "dinner", "entree": "dinner",
    "snack": "snack", "snacks": "snack", "appetizer": "snack", "appetizers": "snack",
    "dessert": "dessert", "desserts": "dessert",
    "side dish": "side", "side": "side", "sides": "side", "salad": "side",
    "sauce": "sauce", "sauces": "sauce", "condiment": "sauce", "dressing": "sauce",
    "drink": "drink", "drinks": "drink", "beverage": "drink", "cocktail": "drink",
}

NUTRITION_MAP = {
    "calories": "calories",
    "calorie": "calories",
    "proteincontent": "protein_g",
    "carbohydratecontent": "carbs_g",
    "fatcontent": "fat_g",
    "fibercontent": "fiber_g",
    "sodiumcontent": "sodium_mg",
    "sugarcontent": "sugar_g",
}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def fetch_html(source: str) -> str:
    """Return HTML from a URL or a local file path."""
    if re.match(r"^https?://", source, re.I):
        request = urllib.request.Request(
            source, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            sys.exit(
                f"error: could not fetch {source}: {exc}\n"
                "       Tip: save the page manually and pass the file path, e.g.\n"
                f"       curl -A 'Mozilla/5.0' -o /tmp/page.html '{source}'\n"
                "       python3 tools/fetch_recipe.py /tmp/page.html"
            )
    path = Path(source)
    if not path.is_file():
        sys.exit(f"error: {source} is neither a URL nor an existing file")
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# JSON-LD extraction
# ---------------------------------------------------------------------------


def extract_jsonld_blocks(html: str) -> list:
    blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    parsed = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        try:
            parsed.append(json.loads(block))
        except json.JSONDecodeError:
            # Retry after stripping trailing commas (common in the wild)
            cleaned = re.sub(r",\s*([\]}])", r"\1", block)
            try:
                parsed.append(json.loads(cleaned))
            except json.JSONDecodeError:
                continue
    return parsed


def find_recipe_object(node):
    """Recursively find a schema.org Recipe dict inside parsed JSON-LD."""
    if isinstance(node, list):
        for item in node:
            found = find_recipe_object(item)
            if found:
                return found
        return None
    if not isinstance(node, dict):
        return None
    node_type = node.get("@type", "")
    types = node_type if isinstance(node_type, list) else [node_type]
    if any(str(t).lower() == "recipe" for t in types):
        return node
    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in node:
            found = find_recipe_object(node[key])
            if found:
                return found
    return None


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def extract_servings(yield_) -> int | None:
    for candidate in as_list(yield_):
        match = re.search(r"\d+", str(candidate))
        if match:
            return int(match.group())
    return None


def extract_instructions(instructions) -> list[str]:
    steps: list[str] = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, str):
            text = node.strip()
            if text:
                steps.append(text)
            return
        if isinstance(node, dict):
            node_type = str(node.get("@type", ""))
            if "itemListElement" in node:  # HowToSection
                walk(node["itemListElement"])
            elif "text" in node and node_type.lower() in ("howtostep", "howtodirection", ""):
                text = str(node["text"]).strip()
                if text:
                    steps.append(text)
            elif "text" in node:
                walk(node["text"])

    walk(instructions)
    # De-duplicate while preserving order
    seen, unique = set(), []
    for step in steps:
        key = step.lower()
        if key not in seen:
            seen.add(key)
            unique.append(step)
    return unique


def extract_nutrition(nutrition: dict | None) -> dict:
    result = {}
    if not isinstance(nutrition, dict):
        return result
    for key, value in nutrition.items():
        mapped = NUTRITION_MAP.get(str(key).replace(" ", "").lower())
        if not mapped or mapped == "sugar_g":
            continue
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if match:
            result[mapped] = f"~{match.group(1)}"
    return result


def extract_author(author) -> str:
    for candidate in as_list(author):
        if isinstance(candidate, dict) and candidate.get("name"):
            return str(candidate["name"])
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def guess_category(raw) -> str:
    for candidate in as_list(raw):
        mapped = CATEGORY_MAP.get(str(candidate).strip().lower())
        if mapped:
            return mapped
    return ""


def extract_image(image) -> str:
    for candidate in as_list(image):
        if isinstance(candidate, str) and candidate.startswith("http"):
            return candidate
        if isinstance(candidate, dict) and str(candidate.get("url", "")).startswith("http"):
            return str(candidate["url"])
    return ""


def html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    # Strip common suffixes like " - Allrecipes" / " | SiteName"
    return re.split(r"\s*[|–-]\s+", title)[0].strip() or title


# ---------------------------------------------------------------------------
# Draft rendering
# ---------------------------------------------------------------------------


def build_draft(recipe: dict, source_url: str, site_name: str) -> tuple[dict, str]:
    title = str(recipe.get("name") or "").strip() or "Untitled recipe"
    ingredients = [str(i).strip() for i in as_list(recipe.get("recipeIngredient")) if str(i).strip()]
    steps = extract_instructions(recipe.get("recipeInstructions"))
    cuisine = ""
    for candidate in as_list(recipe.get("recipeCuisine")):
        cuisine = slugify(str(candidate))
        if cuisine:
            break
    category = guess_category(recipe.get("recipeCategory")) or guess_category(recipe.get("recipeCourse"))
    keywords = recipe.get("keywords") or ""
    tags = [slugify(k) for k in (keywords if isinstance(keywords, list) else str(keywords).split(","))]
    tags = [t for t in tags if t][:8]

    prep = iso_duration_to_minutes(recipe.get("prepTime"))
    cook = iso_duration_to_minutes(recipe.get("cookTime"))
    if cook is None:
        cook = iso_duration_to_minutes(recipe.get("totalTime"))

    meta = {
        "id": "",  # filled by caller
        "title": title,
        "cuisine": cuisine or "other",
        "category": category or "dinner",
        "servings": extract_servings(recipe.get("recipeYield")) or 4,
        "prep_time": prep if prep is not None else 15,
        "cook_time": cook if cook is not None else 30,
        "difficulty": "medium",
        "tags": tags or ["healthy"],
        "status": "draft",
        "source": {
            "name": site_name or "Captured from web",
            "url": source_url or str(recipe.get("url", "") or ""),
            "author": extract_author(recipe.get("author")),
        },        "nutrition": extract_nutrition(recipe.get("nutrition")),
        "created": today(),
        "updated": today(),
    }
    image = extract_image(recipe.get("image"))
    if image:
        meta["image"] = image

    description = re.sub(r"\s+", " ", str(recipe.get("description", ""))).strip()

    todo = []
    if not cuisine or cuisine == "other":
        todo.append("- TODO: cuisine is unset/`other` — assign from the controlled vocabulary")
    if not category:
        todo.append("- TODO: category was not detected — verify `category`")
    if not ingredients:
        todo.append("- TODO: no ingredients extracted — copy them from the source page")
    if not steps:
        todo.append("- TODO: no instructions extracted — copy them from the source page")
    if not meta["nutrition"]:
        todo.append("- TODO: estimate nutrition per serving if feasible (mark with ~)")

    body_lines = [
        f"# {title}",
        "",
        f"> {description or 'TODO: one-sentence hook — what it is, when to make it.'}",
        "",
        "<!-- Draft captured from the web. Standardize, health-audit, and review",
        f"     attribution before publishing (see AGENT.md). Captured {today()}. -->",
        "",
        "## Ingredients",
        "",
    ]
    body_lines += [f"- {item}" for item in ingredients] or ["- TODO"]
    body_lines += ["", "## Instructions", ""]
    if steps:
        body_lines += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
    else:
        body_lines.append("1. TODO")
    body_lines += [
        "",
        "## Notes & Substitutions",
        "",
        "- TODO: at least one lighter swap or dietary substitution (health-audit).",
        *todo,
        "",
        "## Storage & Make-Ahead",
        "",
        "- TODO: fridge/freezer life, reheating, prep-ahead steps.",
        "",
    ]
    return meta, "\n".join(body_lines)


def build_skeleton(source_url: str, site_name: str, title_guess: str) -> tuple[dict, str]:
    """Fallback draft when no JSON-LD recipe was found."""
    title = title_guess or "Untitled recipe"
    meta = {
        "id": "",
        "title": title,
        "cuisine": "other",
        "category": "dinner",
        "servings": 4,
        "prep_time": 15,
        "cook_time": 30,
        "difficulty": "medium",
        "tags": ["healthy"],
        "status": "draft",
        "source": {"name": site_name or "Captured from web", "url": source_url},
        "created": today(),
        "updated": today(),
    }
    body = "\n".join([
        f"# {title}",
        "",
        "> TODO: one-sentence hook — what it is, when to make it.",
        "",
        "<!-- No schema.org Recipe JSON-LD found on the page. Capture the recipe",
        f"     manually from {source_url or 'the source'} and standardize it",
        "     (see AGENT.md and docs/data-model.md). -->",
        "",
        "## Ingredients",
        "",
        "- TODO",
        "",
        "## Instructions",
        "",
        "1. TODO",
        "",
        "## Notes & Substitutions",
        "",
        "- TODO",
        "",
        "## Storage & Make-Ahead",
        "",
        "- TODO",
        "",
    ])
    return meta, body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="recipe page URL or path to a saved HTML file")
    parser.add_argument("--slug", help="override the auto-generated slug")
    parser.add_argument("--output-dir", type=Path, default=RECIPES_DIR)
    parser.add_argument("--stdout", action="store_true", help="print draft to stdout instead of writing")
    args = parser.parse_args()

    html = fetch_html(args.source)
    source_url = args.source if re.match(r"^https?://", args.source, re.I) else ""
    site_name = urlparse(source_url).netloc.removeprefix("www.") if source_url else ""

    recipe = find_recipe_object(extract_jsonld_blocks(html))
    if recipe:
        meta, body = build_draft(recipe, source_url, site_name)
    else:
        print("warning: no schema.org Recipe JSON-LD found — creating a skeleton",
              file=sys.stderr)
        meta, body = build_skeleton(source_url, site_name, html_title(html))

    slug = args.slug or slugify(meta["title"])
    meta["id"] = slug

    content = render_markdown(meta, body)
    if args.stdout:
        print(content, end="")
        return 0

    out_path = args.output_dir / f"{slug}.md"
    if out_path.exists():
        print(f"error: {out_path} already exists", file=sys.stderr)
        return 1
    out_path.write_text(content, encoding="utf-8")

    found = "JSON-LD recipe" if recipe else "skeleton (manual capture needed)"
    print(f"Captured via {found} → {out_path}")
    print(f"  title:     {meta['title']}")
    print(f"  cuisine:   {meta['cuisine']}   category: {meta['category']}")
    print(f"  servings:  {meta['servings']}   times: {meta['prep_time']}+{meta['cook_time']} min")
    print(f"  tags:      {', '.join(meta['tags'])}")
    print("\nNext: standardize + health-audit (AGENT.md), then")
    print("      python3 tools/validate.py && python3 tools/catalog.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
