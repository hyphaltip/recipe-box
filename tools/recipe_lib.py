"""Shared helpers for recipe-box tooling.

Every CLI in tools/ imports this module. Run scripts from the repo root:

    python3 tools/validate.py

Requires: Python 3.10+, PyYAML.
"""
from __future__ import annotations

import datetime
import re
import sys
import unicodedata
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO_ROOT / "recipes"
TEMPLATE_PATH = REPO_ROOT / "templates" / "recipe-template.md"

# ---------------------------------------------------------------------------
# Controlled vocabularies (mirrors docs/data-model.md)
# ---------------------------------------------------------------------------

CATEGORIES = [
    "breakfast", "lunch", "dinner", "snack", "dessert", "side", "sauce", "drink",
    "bread", "pie", "cake", "cinnamon-rolls", "quickbread",
]
DIFFICULTIES = ["easy", "medium", "hard"]
STATUSES = ["draft", "published"]

CUISINES = [
    "afghan", "african", "american", "brazilian", "british", "caribbean", "chinese",
    "ethiopian", "filipino", "french", "german", "greek", "indian", "indonesian",
    "irish", "italian", "japanese", "korean", "lebanese", "mediterranean", "mexican",
    "middle-eastern", "moroccan", "nigerian", "peruvian", "polish", "russian",
    "scandinavian", "senegalese", "spanish", "thai", "turkish", "vietnamese",
    "west-african", "fusion", "other",
]

RECOMMENDED_TAGS = [
    "healthy", "vegetarian", "vegan", "gluten-free", "dairy-free", "nut-free",
    "high-protein", "low-carb", "quick", "one-pan", "batch-cook", "budget",
    "kid-friendly", "meal-prep", "no-cook", "comfort-food", "seasonal", "holiday",
    "grilling", "summer", "winter", "baking", "whole-grain",
]

NUTRITION_KEYS = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sodium_mg"]

REQUIRED_FIELDS = [
    "id", "title", "cuisine", "category", "servings", "prep_time", "cook_time",
    "difficulty", "tags", "status", "source", "created", "updated",
]

# ---------------------------------------------------------------------------
# YAML output: keep `tags` as a flow list for compactness
# ---------------------------------------------------------------------------


class FlowList(list):
    """A list that yaml.safe_dump renders inline: [a, b, c]"""


def _flow_list_representer(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


yaml.SafeDumper.add_representer(FlowList, _flow_list_representer)

# Canonical frontmatter key order
_FRONTMATTER_ORDER = [
    "id", "title", "cuisine", "category", "servings", "prep_time", "cook_time",
    "difficulty", "tags", "status", "image", "source", "nutrition", "created", "updated",
]
_SOURCE_ORDER = ["name", "url", "author", "license"]


def ordered_meta(meta: dict) -> dict:
    """Return a dict with canonical key ordering (and nested source ordering)."""
    out: dict = {}
    for key in _FRONTMATTER_ORDER:
        if key in meta:
            value = meta[key]
            if key == "source" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if v not in (None, "")}
                value = {k: value[k] for k in _SOURCE_ORDER if k in value}
            if key == "tags" and isinstance(value, list):
                value = FlowList(value)
            out[key] = value
    # preserve any keys outside the canonical order
    for key, value in meta.items():
        if key not in out:
            out[key] = value
    return out


def render_markdown(meta: dict, body: str) -> str:
    """Render a complete recipe file: canonical frontmatter + body."""
    fm = yaml.safe_dump(
        ordered_meta(meta),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    ).rstrip("\n")
    return f"---\n{fm}\n---\n\n{body.strip()}\n"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_markdown(text: str) -> tuple[dict, str]:
    """Split a recipe file into (frontmatter dict, body).

    Raises ValueError when the frontmatter block is missing or invalid YAML.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("missing '---' frontmatter block at top of file")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    body = text[match.end():]
    return meta, body


def _normalize_dates(value):
    """Convert YAML auto-parsed datetime.date values into ISO strings."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_dates(v) for v in value]
    return value


def load_recipe(path: Path) -> dict:
    """Load one recipe file -> {slug, path, meta, body}. Raises on parse failure."""
    meta, body = parse_markdown(path.read_text(encoding="utf-8"))
    return {"slug": path.stem, "path": path, "meta": _normalize_dates(meta), "body": body}


def load_all_recipes(verbose: bool = True) -> tuple[list[dict], list[dict]]:
    """Load every recipe in recipes/. Returns (recipes, failures).

    failures is a list of {path, error}. Generated files (catalog.md, README.md)
    are skipped.
    """
    if not RECIPES_DIR.is_dir():
        sys.exit(f"error: {RECIPES_DIR} does not exist — run from repo root")
    recipes, failures = [], []
    for path in sorted(RECIPES_DIR.glob("*.md")):
        if path.name in ("catalog.md", "README.md"):
            continue
        try:
            recipes.append(load_recipe(path))
        except ValueError as exc:
            failures.append({"path": path, "error": str(exc)})
            if verbose:
                print(f"  FAIL {path.name}: {exc}", file=sys.stderr)
    return recipes, failures


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a lowercase-hyphen slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_length].rstrip("-")


def today() -> str:
    return datetime.date.today().isoformat()


def is_iso_date(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def is_number_or_estimate(value) -> bool:
    """Nutrition values may be numbers or '~420'-style estimate strings."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(re.fullmatch(r"~?\d+(\.\d+)?", value.strip()))
    return False


def iso_duration_to_minutes(value) -> int | None:
    """Parse an ISO-8601 duration like 'PT1H30M' into minutes."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value.strip().upper()
    )
    if not match:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    total = days * 1440 + hours * 60 + minutes + seconds / 60
    return round(total) if total else None
