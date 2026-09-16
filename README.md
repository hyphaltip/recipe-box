# 🍳 Recipe Box

A version-controlled database of healthy, culturally diverse recipes. Recipes are
stored as Markdown files with standardized YAML frontmatter — human-readable in
git, machine-readable for tooling and a future web framework.

**Browse the collection live:** <https://meals.stajich.org/>

## Repository layout

```
recipe-box/
├── AGENT.md                 # Operating manual for the recipe-curation agent
├── README.md                # This file
├── LICENSE                  # MIT (tooling code)
├── schema/
│   └── recipe.schema.json   # JSON Schema describing recipe frontmatter
├── templates/
│   └── recipe-template.md   # Canonical recipe template
├── tools/                   # Python 3 CLI tooling (stdlib + PyYAML only)
│   ├── new_recipe.py        # Scaffold a new recipe file
│   ├── fetch_recipe.py      # Capture a recipe from a URL or HTML file
│   ├── validate.py          # Validate every recipe against the standard
│   ├── catalog.py           # Regenerate recipes/catalog.md + recipes/index.json
│   └── build_site.py        # Generate the static website into site/
├── docs/
│   └── data-model.md        # Full field reference & controlled vocabularies
├── recipes/
│   ├── catalog.md           # Generated index (by cuisine → category)
│   ├── index.json           # Generated machine index for the web framework
│   └── <slug>.md            # One file per recipe
└── site/                    # Generated static website (never hand-edited)
    ├── index.html           # Searchable, filterable recipe browser
    ├── recipes/<slug>.html  # One printable page per recipe
    └── assets/style.css     # Shared stylesheet (light/dark, print styles)
```

## Quickstart

```bash
# Scaffold a new recipe interactively
python3 tools/new_recipe.py "Sheet-Pan Miso Salmon" --cuisine japanese --category dinner

# Capture a recipe from the web (extracts schema.org Recipe JSON-LD)
python3 tools/fetch_recipe.py "https://example.com/some-recipe"

# Validate the whole database
python3 tools/validate.py

# Regenerate the catalog after adding/editing recipes
python3 tools/catalog.py

# Build the static website into site/
python3 tools/build_site.py

# Build and preview it at http://localhost:8000
python3 tools/build_site.py --serve
```

All tools support `--help`.

## Recipe format (the standard)

Every recipe is a single Markdown file named `<slug>.md` (lowercase, hyphens).
Machine data lives in YAML frontmatter; the body follows a fixed section order:
Description → Ingredients → Instructions → Notes & Substitutions →
Storage & Make-Ahead. See [`templates/recipe-template.md`](templates/recipe-template.md)
and [`docs/data-model.md`](docs/data-model.md).

## The agent workflow

The curation agent (see [`AGENT.md`](AGENT.md)) follows a five-step loop:

**ACQUIRE → STANDARDIZE → HEALTH-AUDIT → VALIDATE → CATALOG → COMMIT**

Captured recipes always record their source and are adapted (not copied
verbatim) into the standard format.

## Syncing to GitHub

```bash
# One-time setup (or ask the agent to do it once you share the repo URL):
git remote add origin git@github.com:<your-username>/recipe-box.git
git push -u origin main
```

After that, every commit syncs with `git push`. SSH keys or a personal access
token (used by `git` over HTTPS) both work — see
<https://docs.github.com/en/authentication>.

## Deployment (GitHub Pages)

Pushes to `main` that touch `recipes/`, `tools/build_site.py`, or the workflow
file automatically rebuild and deploy the site via
[`.github/workflows/deploy-site.yml`](.github/workflows/deploy-site.yml).
The live site is at <https://meals.stajich.org/> (the default
`hyphaltip.github.io/recipe-box/` URL redirects there; HTTPS is enforced).

### Custom domain

The site serves at `meals.stajich.org` via a CNAME record
(`meals.stajich.org` → `hyphaltip.github.io`) in the `stajich.org` DNS zone,
with the domain attached to the repo's Pages settings and HTTPS enforced:

## Roadmap

- [x] Standardized recipe format + validation
- [x] Web capture tooling (schema.org JSON-LD extraction)
- [x] Generated catalog + JSON index
- [x] Static website with search/filter ([`tools/build_site.py`](tools/build_site.py) → `site/`)
- [x] GitHub Pages deployment with auto-deploy on recipe changes
- [x] Custom domain: <https://meals.stajich.org/>
- [x] Meal plans that reference recipes by slug
- [x] Meal-plan pages on the live site
- [ ] Nutrition estimation for recipes missing it

## License

- Tooling code: MIT (see `LICENSE`)
- Recipes authored for this repo: CC BY 4.0
- Recipes adapted from external sources: remain the property of their original
  authors; attribution is preserved in each recipe's `source` block and they are
  stored for personal use
