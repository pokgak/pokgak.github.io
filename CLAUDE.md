# pokgak.github.io

Personal blog for Aiman Ismail. Plain HTML site built with a single Node.js script — no framework, no bundler.

## Quick Start

```bash
make install   # npm install
make build     # generate HTML and compile CSS → outputs to public/
make preview   # build + serve locally
make clean     # rm -rf public
```

## Orb Browser Testing

Fresh Amp orbs run `.agents/setup`, which installs locked npm dependencies,
installs the Chrome binary used by the orb-provided `agent-browser`, and builds
the site. The supervised preview service is declared in `.amp/services.yaml`.

Start or reconcile the service and print its portal URL:

```bash
amp orb services ensure
```

Run the smoke test against that portal URL:

```bash
npm run test:browser -- https://<portal-url>
```

For a local preview listening on port 3000, run `npm run build && npm run
preview -- 3000`, then run `npm run test:browser`. The test uses an
isolated `agent-browser` session to verify the homepage, theme toggle, primary
navigation, an article page, and the generated agent-discovery files.

## Content Types

There are three content types:

- **Articles** (`content/articles/`) — human-written posts. Agent may assist with fact checking, drafting, or proofreading, but must not author content directly.
- **Notes** (`content/notes/`) — mostly agent-written. Concise, point-based style. Quick publish format for getting ideas out fast with minimal human editing. Not full prose — use bullet points, short paragraphs, direct statements.
- **Experiments** (`content/experiments/`) — fully agent-written research logs. Scientific style: state the question, describe the setup, record observations, draw conclusions. Used as a learning tool especially for topics still being explored (e.g. ML/AI). Compile agent knowledge into the write-up as educational reference.

## Creating a New Article

```bash
make new-article SLUG=my-new-post
```

This creates `content/articles/my-new-post.md` with frontmatter scaffold. Edit the title and add tags.

### Frontmatter

```yaml
---
title: "Your Article Title"
date: 2026-03-13T10:00:00+0800
tags: [tag1, tag2]
---
```

- `title` — displayed on article page and in lists
- `date` — ISO 8601 with timezone offset, used for sorting (newest first)
- `tags` — optional array, rendered as badges on the article page

## Creating a New Note

```bash
make new-note SLUG=my-quick-note
```

Same frontmatter as articles. Notes show a disclaimer on the list page and on each note page.

### Images

Place images in `static/images/` and reference them in markdown as:

```markdown
![alt text](images/filename.png)
```

The build script rewrites `images/` → `/images/` automatically.

## Repo Structure

```
.
├── build.js                  # Build script — templates, markdown rendering, RSS
├── package.json              # Deps and Tailwind build tooling
├── tailwind.config.js        # Tailwind content paths and typography plugin
├── Makefile                  # Build/preview/new-article commands
├── content/
│   ├── articles/             # Human-written articles (YAML frontmatter + body)
│   ├── notes/                # Agent-written quick notes — concise, point-based
│   └── experiments/          # Agent-written research logs — scientific style
├── static/
│   ├── styles.css            # Tailwind entrypoint and syntax theme
│   └── images/               # Images copied to public/images/ during build
├── public/                   # Build output (gitignored)
│   ├── index.html            # Home page
│   ├── index.xml             # RSS feed
│   ├── articles/
│   │   ├── index.html        # Article list page
│   │   └── <slug>/index.html # Individual article pages
│   ├── notes/
│   │   ├── index.html        # Notes list page
│   │   └── <slug>/index.html # Individual note pages
│   ├── experiments/
│   │   ├── index.html        # Experiments list page
│   │   └── <slug>/index.html # Individual experiment pages
│   └── images/
└── .github/workflows/hugo.yml # CI: npm ci + node build.js → GitHub Pages
```

## How the Build Works

`build.js` does everything in one file:

1. Reads all `content/articles/*.md`, `content/notes/*.md`, and `content/experiments/*.md`, parses YAML frontmatter with `gray-matter`
2. Renders markdown → HTML with `marked` + `highlight.js` for syntax highlighting
3. Injects into HTML templates (template literals in build.js)
4. Writes `public/index.html`, `public/articles/…`, `public/notes/…`, `public/experiments/…`
5. Copies `static/images/` → `public/images/`
6. Generates RSS feed at `public/index.xml`
7. Tailwind compiles and minifies `static/styles.css` → `public/styles.css`

## Frontend Stack

- **Tailwind CSS** compiled and minified at build time
- **Vanilla JavaScript** dark mode toggle with localStorage persistence
- **highlight.js** server-side highlighting with bundled GitHub light/dark theme colors
- **@tailwindcss/typography** — prose classes for article content

## Customization

### Changing the layout/templates

All HTML templates are in `build.js` as functions: `baseLayout()`, `homePage()`, `articlesListPage()`, `articlePage()`, `notesListPage()`, `notePage()`. Edit those directly.

### Adding analytics

Replace the `<!-- Analytics placeholder -->` comment in `baseLayout()` inside `build.js` with your tracking script.

### Changing site metadata

Constants at the top of `build.js`: `SITE_TITLE`, `SITE_URL`.

### Social links

Edit the SVG icon links in the `homePage()` function in `build.js`.

## Deployment

Push to `master` → GitHub Actions runs `npm ci && node build.js` → deploys `public/` to GitHub Pages.
