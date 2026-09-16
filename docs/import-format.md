# JSON import format

`tools/import_recipe.py` accepts recipes as JSON and renders them into the
standard Markdown format (see `docs/data-model.md`). It exists so another
agent or script can push recipes into this repo without having to produce
exact Markdown — matching heading text, bullet syntax, frontmatter key
order — by hand. Emit JSON in the shape below; the tool handles rendering,
canonical field ordering, and runs `tools/validate.py` immediately on the
result so mistakes surface right away.

## Shape

One JSON object per recipe (a file may also be a JSON array of several):

```json
{
  "title": "Sheet-Pan Miso Salmon",
  "cuisine": "japanese",
  "category": "dinner",
  "servings": 4,
  "prep_time": 10,
  "cook_time": 20,
  "difficulty": "easy",
  "tags": ["healthy", "quick", "one-pan"],
  "status": "draft",
  "source": { "name": "Original creation" },
  "nutrition": { "calories": "~420", "protein_g": 32 },
  "image": "https://example.com/photo.jpg",
  "hook": "A one-pan dinner ready in half an hour.",
  "ingredients": [
    "4 salmon fillets, skin on",
    "3 tbsp white miso paste"
  ],
  "instructions": [
    "Preheat the oven to 425F (220C).",
    "Whisk miso, mirin, and rice vinegar; brush over salmon."
  ],
  "notes": ["Swap salmon for tofu for a vegan version."],
  "storage": ["Keeps 2 days refrigerated in an airtight container."]
}
```

| Field | Required | Notes |
|---|---|---|
| `title` | ✅ | slug is derived from this unless `id`/`slug` is given |
| `ingredients` | ✅ | list of strings, one per bullet |
| `instructions` | ✅ | list of strings, numbered in order given |
| `cuisine`, `category`, `servings`, `prep_time`, `cook_time`, `difficulty`, `tags`, `source` | — | same rules as `docs/data-model.md`; fall back to the same defaults as `tools/new_recipe.py` (`difficulty: medium`, `status: draft`, `tags: [healthy]`, `source.name: "Original creation"`) if omitted |
| `hook` | — | one-sentence blockquote; a TODO placeholder is inserted if missing |
| `notes`, `storage` | — | lists of strings; sections are emitted even if empty |
| `nutrition`, `image` | — | passed through as-is when present |
| `id` / `slug` | — | overrides the auto-generated slug |
| `created`, `updated` | — | ISO dates; default to today |
| `status` | — | `draft` (default) or `published`; `--publish` on the CLI forces it |

Anything not on this list is ignored — there's no need to omit unknown keys
defensively.

## Usage

```bash
python3 tools/import_recipe.py recipe.json                 # one recipe
python3 tools/import_recipe.py batch.json                  # a JSON array of recipes
python3 tools/import_recipe.py --dir incoming/               # every *.json in a directory
python3 tools/import_recipe.py recipe.json --dry-run          # preview, write nothing
cat recipe.json | python3 tools/import_recipe.py -            # stdin
```

Each write is immediately validated; the process exits non-zero if any
recipe fails. Existing files are never overwritten unless `--force` is
passed. After a successful import, still run the normal pipeline:

```bash
python3 tools/validate.py && python3 tools/catalog.py && python3 tools/build_site.py
```

Recipes land with `status: draft` by default — they still need the
HEALTH-AUDIT pass from `AGENT.md` (a lighter swap or dietary substitution
note, an honest cuisine/category, nutrition estimate) before being flipped to
`published` and committed.
