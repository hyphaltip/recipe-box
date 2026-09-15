# Recipes

One Markdown file per recipe, named `<slug>.md` (lowercase, hyphens). The
`id` frontmatter field must equal the filename stem, and slugs never change
after publication — other documents (meal plans, the web UI) link by slug.

- Format reference: [`docs/data-model.md`](../docs/data-model.md)
- Template: [`templates/recipe-template.md`](../templates/recipe-template.md)
- Workflow: [`AGENT.md`](../AGENT.md)

## Generated files (do not hand-edit)

- `catalog.md` — human index grouped by cuisine
- `index.json` — machine index for the web framework

Regenerate both after any change: `python3 tools/catalog.py`
