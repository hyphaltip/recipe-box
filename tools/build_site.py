#!/usr/bin/env python3
"""Build the recipe-box static website into site/.

Renders every published recipe to a standalone HTML page plus a filterable,
searchable index page. Zero dependencies beyond the repo's recipe_lib
(stdlib + PyYAML). All recipe data is embedded in the index page, so search
and filtering work from file:// with no server.

Usage:
    python3 tools/build_site.py            # build site/
    python3 tools/build_site.py --serve    # build, then serve on :8000
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from collections import Counter
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from recipe_lib import REPO_ROOT, load_all_recipes

SITE_DIR = REPO_ROOT / "site"
GITHUB_BASE = "https://github.com/hyphaltip/recipe-box"

CATEGORY_ORDER = ["breakfast", "lunch", "dinner", "side", "snack", "dessert", "sauce", "drink"]
DIET_TAGS = ["vegan", "vegetarian", "gluten-free", "dairy-free", "high-protein", "quick", "one-pan", "budget"]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def json_for_script(obj) -> str:
    """JSON safe to embed in a <script> block."""
    return json.dumps(obj, ensure_ascii=False, indent=None).replace("</", "<\\/")


# ---------------------------------------------------------------------------
# Markdown (our constrained dialect) -> HTML
# ---------------------------------------------------------------------------

def inline_md(text: str) -> str:
    """Render inline markdown: bold, links. .md links become .html."""
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

    def link(match):
        label, target = match.group(1), match.group(2)
        if target.startswith("http"):
            return f'<a href="{target}" rel="noopener">{label}</a>'
        target = re.sub(r"\.md$", ".html", target)
        return f'<a href="{target}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    return text


def parse_body(body: str) -> dict:
    """Parse a recipe body into {hook, sections: [{heading, blocks}]}.

    blocks are ("ul"|"ol"|"p", [items]) with multi-line list items joined.
    """
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    hook_lines: list[str] = []
    sections: list[dict] = []
    current: dict | None = None

    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()

        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue  # H1 comes from frontmatter

        if stripped.startswith("> "):
            if current is None:
                hook_lines.append(stripped[2:])
            continue

        if stripped.startswith("## "):
            current = {"heading": stripped[3:].strip(), "blocks": []}
            sections.append(current)
            continue

        if current is None:
            hook_lines.append(stripped)
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        step = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        indent = len(line) - len(line.lstrip())

        if bullet:
            current["blocks"].append(["ul", [bullet.group(1)]])
        elif step:
            current["blocks"].append(["ol", [step.group(2)]])
        elif current["blocks"] and indent >= 2:
            current["blocks"][-1][1][-1] += " " + stripped
        elif current["blocks"] and current["blocks"][-1][0] == "p":
            current["blocks"][-1][1][-1] += " " + stripped
        else:
            current["blocks"].append(["p", [stripped]])

    return {"hook": " ".join(hook_lines), "sections": sections}


def render_sections(sections: list[dict]) -> str:
    out = []
    for section in sections:
        out.append(f'<section class="rsection">\n<h2>{inline_md(section["heading"])}</h2>')
        # Coalesce consecutive blocks of the same kind into one list
        merged: list[tuple[str, list[str]]] = []
        for kind, items in section["blocks"]:
            if merged and merged[-1][0] == kind and kind in ("ul", "ol"):
                merged[-1][1].extend(items)
            else:
                merged.append((kind, list(items)))
        for kind, items in merged:
            if kind == "ul":
                lis = "".join(f"<li>{inline_md(item)}</li>" for item in items)
                out.append(f"<ul>{lis}</ul>")
            elif kind == "ol":
                lis = "".join(f"<li>{inline_md(item)}</li>" for item in items)
                out.append(f'<ol class="steps">{lis}</ol>')
            else:
                out.append("".join(f"<p>{inline_md(item)}</p>" for item in items))
        out.append("</section>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

STYLESHEET = """
:root {
  --bg: #faf6f0; --card: #fffdf9; --ink: #2a2724; --muted: #7a6f63;
  --accent: #c14f2c; --accent-soft: #f3ddd2; --line: #e8dfd3;
  --good: #4a7c59; --shadow: 0 1px 3px rgba(60, 45, 30, 0.08), 0 4px 14px rgba(60, 45, 30, 0.06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #211d19; --card: #2b2620; --ink: #ece5da; --muted: #a49686;
    --accent: #e0704a; --accent-soft: #3a2c24; --line: #3d362e;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.4), 0 4px 14px rgba(0, 0, 0, 0.3);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif;
}
h1, h2, h3, .serif { font-family: ui-serif, Georgia, "Times New Roman", serif; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 20px; }

/* ---------- index ---------- */
.hero { padding: 44px 0 10px; }
.hero h1 { margin: 0 0 6px; font-size: clamp(30px, 5vw, 44px); }
.hero .tagline { color: var(--muted); margin: 0 0 14px; font-size: 1.05rem; }
.stats { display: flex; gap: 18px; flex-wrap: wrap; color: var(--muted); font-size: 0.92rem; }
.stats b { color: var(--ink); font-size: 1.15rem; font-family: ui-serif, Georgia, serif; }

.controls {
  position: sticky; top: 0; z-index: 10; background: var(--bg);
  padding: 12px 0 10px; border-bottom: 1px solid var(--line); margin-bottom: 22px;
}
.controls .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
#q {
  flex: 1 1 220px; padding: 10px 14px; border: 1px solid var(--line); border-radius: 10px;
  background: var(--card); color: var(--ink); font-size: 1rem;
}
#q:focus { outline: 2px solid var(--accent-soft); border-color: var(--accent); }
select {
  padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px;
  background: var(--card); color: var(--ink); font-size: 0.95rem;
}
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.chip {
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
  border-radius: 999px; padding: 5px 13px; font-size: 0.88rem; cursor: pointer;
  user-select: none; transition: all 0.12s ease;
}
.chip:hover { border-color: var(--accent); }
.chip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.count { color: var(--muted); font-size: 0.9rem; margin: 6px 0 14px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 18px; padding-bottom: 60px; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  overflow: hidden; box-shadow: var(--shadow); display: flex; flex-direction: column;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.card:hover { transform: translateY(-3px); text-decoration: none; }
.card .thumb { height: 130px; background: linear-gradient(135deg, var(--accent-soft), var(--line)); }
.card .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card .body { padding: 14px 16px 16px; display: flex; flex-direction: column; gap: 7px; flex: 1; }
.card .cuisine {
  color: var(--accent); font-size: 0.75rem; text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 600;
}
.card h3 { margin: 0; font-size: 1.18rem; line-height: 1.3; color: var(--ink); }
.card:hover h3 { color: var(--accent); }
.card .meta { color: var(--muted); font-size: 0.85rem; }
.card .snip { color: var(--muted); font-size: 0.9rem; margin: 0; flex: 1; }
.pills { display: flex; gap: 6px; flex-wrap: wrap; }
.pill {
  background: var(--accent-soft); color: var(--ink); font-size: 0.74rem;
  border-radius: 999px; padding: 2px 9px;
}
.empty { padding: 60px 0; text-align: center; color: var(--muted); display: none; }

/* ---------- recipe page ---------- */
.rtop { display: flex; justify-content: space-between; align-items: center; padding: 20px 0 0; gap: 10px; }
.back { font-size: 0.95rem; }
button.plain {
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
  border-radius: 10px; padding: 8px 14px; font-size: 0.9rem; cursor: pointer;
}
button.plain:hover { border-color: var(--accent); color: var(--accent); }
.rhead { padding: 18px 0 8px; }
.rhead h1 { margin: 10px 0 10px; font-size: clamp(28px, 4.5vw, 40px); line-height: 1.15; }
.rhead .hook { color: var(--muted); font-size: 1.08rem; font-style: italic; margin: 0 0 14px; max-width: 62ch; }
.rmeta { display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.92rem; color: var(--muted); }
.rmeta b { color: var(--ink); }
.cols { display: grid; grid-template-columns: 330px 1fr; gap: 34px; align-items: start; padding-bottom: 60px; }
aside.raside { position: sticky; top: 20px; display: flex; flex-direction: column; gap: 18px; }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; box-shadow: var(--shadow); }
.panel h2 { margin: 0 0 10px; font-size: 1.15rem; }
.panel ul { margin: 0; padding-left: 18px; }
.panel li { margin: 7px 0; font-size: 0.96rem; }
.nutri { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; }
.nutri div b { display: block; font-size: 1.05rem; font-family: ui-serif, Georgia, serif; }
.nutri div { font-size: 0.8rem; color: var(--muted); }
.rsection { margin: 0 0 28px; }
.rsection h2 {
  font-size: 1.3rem; margin: 0 0 12px; padding-bottom: 6px;
  border-bottom: 2px solid var(--accent-soft);
}
ol.steps { counter-reset: step; list-style: none; margin: 0; padding: 0; }
ol.steps li { counter-increment: step; position: relative; padding-left: 44px; margin: 0 0 16px; }
ol.steps li::before {
  content: counter(step);
  position: absolute; left: 0; top: 1px; width: 28px; height: 28px;
  background: var(--accent); color: #fff; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.85rem; font-weight: 700;
}
.rsection ul { padding-left: 20px; }
.rsection li { margin: 6px 0; }
.sourcebox { margin-top: 34px; padding-top: 14px; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.88rem; }
footer.site { padding: 26px 0 40px; color: var(--muted); font-size: 0.85rem; border-top: 1px solid var(--line); }

@media (max-width: 820px) {
  .cols { grid-template-columns: 1fr; }
  aside.raside { position: static; }
}

@media print {
  body { background: #fff; color: #000; font-size: 12pt; }
  .controls, .rtop, .card .thumb, footer.site, .back { display: none !important; }
  .card, .panel { box-shadow: none; border-color: #ccc; }
  .cols { grid-template-columns: 1fr; gap: 12px; }
  aside.raside { position: static; }
}
"""


def nutrition_rows(nutrition: dict | None) -> list[tuple[str, str]]:
    if not nutrition:
        return []
    labels = {
        "calories": "Calories", "protein_g": "Protein (g)", "carbs_g": "Carbs (g)",
        "fat_g": "Fat (g)", "fiber_g": "Fiber (g)", "sodium_mg": "Sodium (mg)",
    }
    return [(labels[k], v) for k, v in nutrition.items() if k in labels]


def source_line(meta: dict) -> str:
    source = meta.get("source", {})
    name = source.get("name", "")
    url = source.get("url", "")
    author = source.get("author", "")
    if name == "Original creation":
        text = "Original recipe for this collection (CC BY 4.0)."
    else:
        linked = f'<a href="{esc(url)}" rel="noopener">{esc(name)}</a>' if url else esc(name)
        text = f"Adapted from {linked}"
        if author:
            text += f" by {esc(author)}"
    return text


def total_minutes(meta: dict) -> int:
    return int(meta.get("prep_time") or 0) + int(meta.get("cook_time") or 0)


def recipe_page(recipe: dict) -> str:
    meta, body = recipe["meta"], recipe["body"]
    parsed = parse_body(body)
    slug = recipe["slug"]
    title = esc(meta["title"])

    meta_bits = [
        f"<span><b>{total_minutes(meta)} min</b> total ({meta.get('prep_time', '?')} prep + {meta.get('cook_time', '?')} cook)</span>",
        f"<span><b>{esc(meta.get('servings', '?'))}</b> servings</span>",
        f"<span><b>{esc(meta.get('difficulty', '?'))}</b> difficulty</span>",
        f"<span>{esc(meta.get('cuisine', '').replace('-', ' ').title())} · {esc(meta.get('category', ''))}</span>",
    ]

    nutri_html = ""
    rows = nutrition_rows(meta.get("nutrition"))
    if rows:
        cells = "".join(f"<div><b>{esc(v)}</b>{esc(k)}</div>" for k, v in rows)
        nutri_html = f'<div class="panel"><h2>Nutrition <small style="font-weight:400;color:var(--muted)">per serving (~ est.)</small></h2><div class="nutri">{cells}</div></div>'

    ingredients_html = ""
    for section in parsed["sections"]:
        if section["heading"].lower().startswith("ingredients"):
            items = [item for kind, its in section["blocks"] if kind == "ul" for item in its]
            if items:
                lis = "".join(f"<li>{inline_md(i)}</li>" for i in items)
                ingredients_html = f'<div class="panel"><h2>Ingredients</h2><ul>{lis}</ul></div>'

    main_sections = [
        s for s in parsed["sections"] if not s["heading"].lower().startswith("ingredients")
    ]

    github_link = f'<a href="{GITHUB_BASE}/blob/main/recipes/{esc(slug)}.md" rel="noopener">view source on GitHub</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Recipe Box</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="wrap">
  <div class="rtop">
    <a class="back" href="../index.html">← All recipes</a>
    <button class="plain" onclick="window.print()">Print recipe</button>
  </div>
  <header class="rhead">
    <div class="pills">
      <span class="pill">{esc(meta.get('cuisine', '').replace('-', ' ').title())}</span>
      <span class="pill">{esc(meta.get('category', ''))}</span>
    </div>
    <h1>{title}</h1>
    <p class="hook">{inline_md(parsed['hook'])}</p>
    <div class="rmeta">{''.join(meta_bits)}</div>
  </header>
  <div class="cols">
    <aside class="raside">
      {ingredients_html}
      {nutri_html}
    </aside>
    <article>
      {render_sections(main_sections)}
      <div class="sourcebox">{source_line(meta)} · {github_link}</div>
    </article>
  </div>
  <footer class="site">Recipe Box · built from the recipe database · {esc(meta.get('updated', ''))}</footer>
</div>
</body>
</html>
"""


def card_data(recipes: list[dict]) -> list[dict]:
    out = []
    for recipe in recipes:
        meta = recipe["meta"]
        parsed = parse_body(recipe["body"])
        ingredients = [
            item for section in parsed["sections"]
            if section["heading"].lower().startswith("ingredients")
            for kind, items in section["blocks"] if kind == "ul" for item in items
        ]
        out.append({
            "slug": recipe["slug"],
            "title": meta["title"],
            "cuisine": meta.get("cuisine", "other"),
            "category": meta.get("category", "dinner"),
            "servings": meta.get("servings"),
            "total": total_minutes(meta),
            "difficulty": meta.get("difficulty", "easy"),
            "tags": meta.get("tags", []),
            "image": meta.get("image", ""),
            "hook": parsed["hook"],
            "ingredients": ingredients,
            "created": str(meta.get("created", "")),
        })
    return out


def index_page(recipes: list[dict]) -> str:
    data = card_data(recipes)
    cuisines = sorted({r["cuisine"] for r in data})
    categories = [c for c in CATEGORY_ORDER if any(r["category"] == c for r in data)]
    diets = [t for t in DIET_TAGS if any(t in r["tags"] for r in data)]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recipe Box · {len(data)} healthy recipes from around the world</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>Recipe Box</h1>
    <p class="tagline">Healthy, culturally diverse home cooking — captured, standardized, and version-controlled.</p>
    <div class="stats">
      <span><b>{len(data)}</b> recipes</span>
      <span><b>{len(cuisines)}</b> cuisines</span>
      <span><b>{sum(1 for r in data if r['total'] <= 30)}</b> ready in 30 min</span>
      <span><b>{sum(1 for r in data if 'vegan' in r['tags'])}</b> vegan</span>
      <span><b>{sum(1 for r in data if 'vegetarian' in r['tags'])}</b> vegetarian</span>
    </div>
  </header>

  <div class="controls">
    <div class="row">
      <input id="q" type="search" placeholder="Search recipes or ingredients…" autocomplete="off">
      <select id="cuisine">
        <option value="all">All cuisines</option>
        {''.join(f'<option value="{c}">{esc(c.replace("-", " ").title())}</option>' for c in cuisines)}
      </select>
      <select id="sort">
        <option value="title">Sort: A–Z</option>
        <option value="time">Sort: fastest</option>
        <option value="new">Sort: newest</option>
      </select>
    </div>
    <div class="chips" id="catchips">
      {''.join(f'<button class="chip" data-cat="{c}">{c}</button>' for c in categories)}
    </div>
    <div class="chips" id="dietchips">
      {''.join(f'<button class="chip" data-tag="{t}">{t}</button>' for t in diets)}
    </div>
  </div>

  <p class="count" id="count"></p>
  <main class="grid" id="grid"></main>
  <div class="empty" id="empty">No recipes match — try clearing a filter.</div>

  <footer class="site">Recipe Box · regenerated from the recipe database ·
    <a href="{GITHUB_BASE}" rel="noopener">on GitHub</a></footer>
</div>

<script>
const RECIPES = {json_for_script(data)};
const grid = document.getElementById('grid');
const countEl = document.getElementById('count');
const state = {{ q: '', cuisine: 'all', cats: new Set(), tags: new Set(), sort: 'title' }};

function pillHtml(tags) {{
  return tags.slice(0, 4).map(t => `<span class="pill">${{t}}</span>`).join('');
}}

function cardHtml(r) {{
  const thumb = r.image
    ? `<img src="${{r.image}}" alt="" loading="lazy">`
    : '';
  const min = r.total;
  return `<a class="card" href="recipes/${{r.slug}}.html">
    <div class="thumb">${{thumb}}</div>
    <div class="body">
      <div class="cuisine">${{r.cuisine.replace('-', ' ')}}</div>
      <h3>${{r.title}}</h3>
      <div class="meta">${{r.category}} · ${{min}} min · serves ${{r.servings}} · ${{r.difficulty}}</div>
      <p class="snip">${{r.hook}}</p>
      <div class="pills">${{pillHtml(r.tags)}}</div>
    </div>
  </a>`;
}}

function render() {{
  const q = state.q.toLowerCase();
  let list = RECIPES.filter(r => {{
    if (state.cuisine !== 'all' && r.cuisine !== state.cuisine) return false;
    for (const c of state.cats) if (r.category !== c) return false;
    for (const t of state.tags) if (!r.tags.includes(t)) return false;
    if (q) {{
      const hay = (r.title + ' ' + r.cuisine + ' ' + r.category + ' ' +
        r.tags.join(' ') + ' ' + r.ingredients.join(' ') + ' ' + r.hook).toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});
  if (state.sort === 'time') list.sort((a, b) => a.total - b.total);
  else if (state.sort === 'new') list.sort((a, b) => b.created.localeCompare(a.created));
  else list.sort((a, b) => a.title.localeCompare(b.title));

  grid.innerHTML = list.map(cardHtml).join('');
  countEl.textContent = `Showing ${{list.length}} of ${{RECIPES.length}} recipes`;
  document.getElementById('empty').style.display = list.length ? 'none' : 'block';
}}

document.getElementById('q').addEventListener('input', e => {{ state.q = e.target.value; render(); }});
document.getElementById('cuisine').addEventListener('change', e => {{ state.cuisine = e.target.value; render(); }});
document.getElementById('sort').addEventListener('change', e => {{ state.sort = e.target.value; render(); }});
for (const btn of document.querySelectorAll('#catchips .chip')) {{
  btn.addEventListener('click', () => {{
    const c = btn.dataset.cat;
    state.cats.has(c) ? state.cats.delete(c) : state.cats.add(c);
    btn.classList.toggle('on');
    render();
  }});
}}
for (const btn of document.querySelectorAll('#dietchips .chip')) {{
  btn.addEventListener('click', () => {{
    const t = btn.dataset.tag;
    state.tags.has(t) ? state.tags.delete(t) : state.tags.add(t);
    btn.classList.toggle('on');
    render();
  }});
}}
render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build() -> list[dict]:
    recipes, failures = load_all_recipes(verbose=False)
    if failures:
        for failure in failures:
            print(f"  unparseable: {failure['path'].name}: {failure['error']}", file=sys.stderr)
        sys.exit("error: fix unparseable recipes before building the site")

    published = [r for r in recipes if r["meta"].get("status") == "published"]
    if not published:
        sys.exit("error: no published recipes to build")

    assets = SITE_DIR / "assets"
    pages_dir = SITE_DIR / "recipes"
    pages_dir.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)

    # Remove stale recipe pages (deleted recipes shouldn't linger)
    for old in pages_dir.glob("*.html"):
        old.unlink()

    for recipe in published:
        (pages_dir / f"{recipe['slug']}.html").write_text(recipe_page(recipe), encoding="utf-8")

    (SITE_DIR / "index.html").write_text(index_page(published), encoding="utf-8")
    (assets / "style.css").write_text(STYLESHEET.strip() + "\n", encoding="utf-8")

    print(f"Site built → {SITE_DIR}")
    print(f"  {len(published)} recipe pages · index.html · assets/style.css")
    return published


def serve() -> None:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    print("Serving site/ at http://localhost:8000 (Ctrl+C to stop)")
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serve", action="store_true", help="after building, serve on http://localhost:8000")
    args = parser.parse_args()
    build()
    if args.serve:
        serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
