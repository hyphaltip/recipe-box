# Recipe Curation Agent Manual

This is the operating manual for the recipe-curation agent. Follow it whenever
adding or editing recipes in this repository. The goal: a healthy,
culturally diverse, well-attributed recipe database that stays clean as it grows.

## Mission

Build a database of healthy recipes with variety across world cuisines —
lean proteins, legumes, whole grains, plenty of vegetables, healthy fats, and
lighter cooking methods (roasting, steaming, stir-frying, braising). Every
recipe is standardized, attributed, validated, and cataloged.

## The workflow

For every new recipe, run this loop end-to-end. Do not skip steps.

### 1. ACQUIRE

Get the raw recipe by one of these routes:

- **From a URL**: `python3 tools/fetch_recipe.py <url>` — extracts the
  schema.org Recipe JSON-LD embedded in most recipe sites into a draft file.
  If the site blocks fetches, save the page HTML locally and pass the file path.
- **From text a user pastes**: scaffold with
  `python3 tools/new_recipe.py "<title>" --cuisine <cuisine> --category <category>`
  and paste content into the right sections.
- **Original creation**: author it directly from the template.

### 2. STANDARDIZE

Transform the draft into the standard format (see `docs/data-model.md`):

- **Title**: appetizing but honest; can be adapted from the source title.
- **Slug/filename**: lowercase-hyphens, short, stable. Must equal `id`.
- **Ingredients**: one per line, format `quantity unit ingredient, prep`
  (e.g., `2 cups kale, stemmed and chopped`). Add both volume and weight for
  baking. Convert obscure units to metric+US where practical.
- **Instructions**: numbered steps, each a complete actionable sentence; fold
  multiple micro-steps into one step when they're one motion. State visual/tactile
  cues ("until golden, 4–5 min") alongside times.
- **Cuisine**: pick from the controlled vocabulary in `docs/data-model.md`
  (closest match; `other` if truly hybrid — note it in the description).
- **Category**: breakfast / lunch / dinner / snack / dessert / side / sauce / drink.
- **Tags**: use recommended vocabulary (vegetarian, vegan, gluten-free, dairy-free,
  high-protein, quick, one-pan, batch-cook, budget, meal-prep, ...). Don't invent
  near-duplicates; `quick` means total time ≤ 30 min.
- **Source**: ALWAYS fill `source.name` and `source.url` for anything adapted.
  Set `source.license: CC-BY-4.0` only for recipes authored for this repo.

**Attribution rule**: adapt, don't copy. Reorganize, reword, and standardize
captured recipes; keep the source link. Never paste a recipe's prose verbatim.

### 3. HEALTH-AUDIT

This box skews healthy. After standardizing:

- If the recipe is heavy (fried, cream-laden, sugary), either adapt it
  (air-fry/bake alternatives, yogurt for cream, reduce sugar) or skip it.
- Add a **Notes & Substitutions** bullet with at least one lighter swap or a
  common dietary substitution (gluten-free / dairy-free / vegan option).
- Estimate nutrition per serving when feasible and mark estimates as such
  (`~` prefix, e.g. `calories: ~420`). Leave the block out rather than guess badly.

### 4. VALIDATE

```bash
python3 tools/validate.py
```

Zero errors required. Warnings are judgment calls — fix the ones that matter
(missing tags, unknown cuisine) and ignore trivia. A recipe with `status: draft`
may fail validation quietly in your working tree, but **only `status: published`
recipes may be committed**.

### 5. CATALOG

```bash
python3 tools/catalog.py
```

Regenerates `recipes/catalog.md` and `recipes/index.json`. Commit the regenerated
files together with the recipe.

### 5b. BUILD SITE

```bash
python3 tools/build_site.py
```

Regenerates `site/` (index + one page per published recipe). Commit the
regenerated site alongside the recipe when it should be visible on the web.
Like the catalog, `site/` is generated — never hand-edit it. Run
`python3 tools/build_site.py --serve` to preview at http://localhost:8000.

### 6. COMMIT

Conventional commits, one recipe per commit (plus its catalog update):

```
recipe: add sheet-pan-miso-salmon
recipe: update shakshuka ( nutrition, tag fixes)
chore: regenerate catalog
docs: expand controlled vocabulary
```

Never rewrite published history (`main` only moves forward).

## Variety discipline

When building collections or meal plans, rotate cuisines and categories — aim for
no more than two recipes from the same cuisine in a row, and cover the week's
categories: breakfast, lunch, dinner, sides, and at least one snack or dessert.
Lean on overlapping base ingredients (onions, garlic, canned beans, grains,
eggs, canned tomatoes, spice blends) so shopping stays efficient.

## Meal plans (future)

Meal plans will live in `meal-plans/` and reference recipes by slug. A plan week
must: cover 7 days × (breakfast, lunch, dinner), use each dinner's leftovers in a
following lunch where sensible, include a Sunday prep list, and ship with a
grocery list grouped by store section.

## Editing rules

- `id` and filename never change after publication (links depend on them).
- Corrections to a published recipe bump `updated:` and note the change in the
  commit message.
- Don't delete published recipes; ask the owner first.
