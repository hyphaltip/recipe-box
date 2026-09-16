# images/

Locally-hosted recipe photos we actually own — an original creation, or a
photo we took ourselves. Filename must be `<slug>.<ext>` matching the
recipe's `id`/filename, with `ext` one of `jpg`, `jpeg`, `png`, or `webp`
(e.g. `images/mediterranean-lentil-sweet-potato-soup.jpg`).

Reference it from the recipe's frontmatter:

```yaml
image: images/mediterranean-lentil-sweet-potato-soup.jpg
```

`tools/build_site.py` copies this directory into `site/assets/images/` on
every build, and both the index card and the recipe page render it.

**Don't put someone else's photo here.** A recipe adapted from another site
keeps its `image` field as that site's `http(s)` URL (hotlinked, not
downloaded) — see `docs/data-model.md` and the STANDARDIZE step in
`AGENT.md` for the full convention.
