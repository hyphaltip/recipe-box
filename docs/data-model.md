# Recipe Data Model

Every recipe is one Markdown file: `recipes/<slug>.md`, where `<slug>` is
lowercase with hyphens (e.g., `tuscan-white-bean-kale-soup.md`). The `id`
frontmatter field MUST equal the filename stem.

## Frontmatter fields

| Field | Required | Type | Rules |
|---|---|---|---|
| `id` | ✅ | string | slug; equals filename stem |
| `title` | ✅ | string | human-readable |
| `cuisine` | ✅ | string | controlled vocabulary (below); lowercase-hyphen |
| `category` | ✅ | enum | `breakfast` `lunch` `dinner` `snack` `dessert` `side` `sauce` `drink` `bread` `pie` `cake` `cinnamon-rolls` `quickbread` |
| `servings` | ✅ | integer | ≥ 1 |
| `prep_time` | ✅ | integer | minutes, ≥ 0 |
| `cook_time` | ✅ | integer | minutes, ≥ 0 |
| `difficulty` | ✅ | enum | `easy` `medium` `hard` |
| `tags` | ✅ | list | recommended vocabulary (below) |
| `status` | ✅ | enum | `draft` `published` |
| `source` | ✅ | map | `name` required; `url`, `author`, `license` optional |
| `nutrition` | — | map | per serving: `calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sodium_mg` (numbers; prefix estimates with `~` as a string, e.g. `calories: "~420"`) |
| `created` | ✅ | date | ISO `YYYY-MM-DD` |
| `updated` | ✅ | date | ISO; ≥ `created` |
| `image` | — | string | http(s) URL, or a local `images/<slug>.<ext>` path |

> The optional `image` field holds a representative photo, rendered on the
> index card and recipe page. It's either an `http(s)` URL — used for
> recipes adapted from another site, hotlinked rather than re-hosted, since
> the photo belongs to that site — or a local `images/<slug>.<ext>` path
> (jpg/jpeg/png/webp) for a photo we actually own (an original creation, or
> one you took yourself), committed to the repo under the top-level
> `images/` directory and copied into `site/assets/images/` at build time.
> Recipes may also embed images in the body via standard Markdown syntax.

## Body structure (fixed section order)

```markdown
# <Title>

> One-sentence hook: what it is, when to make it.

## Ingredients

- 2 tbsp olive oil
- ...

## Instructions

1. ...
2. ...

## Notes & Substitutions

- Swap notes, dietary substitutions, lighter variants.

## Storage & Make-Ahead

- Fridge/freezer life, reheating, prep-ahead steps.
```

- Ingredients: one per bullet, format `quantity unit ingredient, prep note`.
- Instructions: numbered; each step one complete action with a doneness cue.

## Controlled vocabulary

### Cuisine (`cuisine`)

`afghan` `african` `american` `brazilian` `british` `caribbean` `chinese`
`ethiopian` `filipino` `french` `german` `greek` `indian` `indonesian`
`irish` `italian` `japanese` `korean` `lebanese` `mediterranean` `mexican`
`middle-eastern` `moroccan`
`nigerian` `peruvian` `polish` `russian` `scandinavian` `senegalese`
`spanish` `thai` `turkish` `vietnamese` `west-african` `fusion` `other`
Unknown cuisines produce a validation **warning** (not an error) — propose new
entries to the vocabulary via a `docs:` commit rather than inventing synonyms.

### Tags (`tags`)

`healthy` `vegetarian` `vegan` `gluten-free` `dairy-free` `nut-free`
`high-protein` `low-carb` `quick` `one-pan` `batch-cook` `budget` `kid-friendly`
`meal-prep` `no-cook` `comfort-food` `seasonal` `holiday` `grilling` `summer`
`winter` `baking` `whole-grain`

- `quick` = total time (prep + cook) ≤ 30 minutes
- `one-pan` = single pan/sheet/trust-pot cooking vessel

### Difficulty

- `easy` — under 30 min active, common techniques
- `medium` — longer technique or multi-step process
- `hard` — advanced technique, timing-critical, or multi-day

## Generated files (do not hand-edit)

- `recipes/catalog.md` — human index grouped by cuisine → category
- `recipes/index.json` — machine index (array of frontmatter + `slug` + `file`)

Regenerate with `python3 tools/catalog.py` after any recipe change.
