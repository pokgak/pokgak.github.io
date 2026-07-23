# pokgak.github.io

Personal blog for Aiman Ismail. Plain HTML site built with a single Node.js script — no framework, no bundler.

## Quick Start

```bash
make install   # npm install
make build     # node build.js → outputs to public/
make preview   # build + serve locally
make clean     # rm -rf public
```

## Content Types

There are three content types:

- **Articles** (`content/articles/`) — human-written posts. Agent may assist with fact checking, drafting, or proofreading, but must not author content directly.
- **Notes** (`content/notes/`) — mostly agent-written. Concise, point-based style. Quick publish format for getting ideas out fast with minimal human editing. Not full prose — use bullet points, short paragraphs, direct statements.
- **Experiments** (`content/experiments/`) — fully agent-written research logs. Scientific style: state the question, describe the setup, record observations, draw conclusions. Used as a learning tool especially for topics still being explored (e.g. ML/AI). Compile agent knowledge into the write-up as educational reference.

## Writing Style — Notes & Experiments

Applies to `content/notes/` and `content/experiments/`. Use these rules to rework
existing pieces and as the default for new ones. These are technical, analytical,
voiced documents (first-person, occasional dry humour) — *explanation* documents in
the Diátaxis sense, understanding-oriented and discursive, allowed to weigh
alternatives and narrate reasoning. They are NOT how-to guides. Do not flatten them.

### The one decision that governs everything: classify each block first

Before editing any block, decide which mode it is in. A single piece contains both.

- **Procedural** — setup steps, fix instructions, "do X then Y", config blocks and
  the sentences that operate them, migration/rollout sequences. Reader will *execute*
  this. → apply **Procedural rules**.
- **Analytical** — problem framing, root-cause reasoning, tradeoff discussion,
  debugging narrative, takeaways, anything with a "because" or a "turned out to be".
  Reader will *understand* this, not run it. → apply **Analytical rules**.

When in doubt, treat it as analytical. Over-proceduralising analysis is the main
failure mode; it strips the reasoning and the voice.

### Procedural rules (borrowed from ASD-STE100, applied loosely)

Goal: unambiguous, executable, skimmable. Voice is not needed here.

1. **One instruction per sentence.** Split compound steps.
2. **Imperative mood.** "Restart the nodes", not "restarting the nodes means…".
3. **Sequential steps as a numbered list**, in execution order.
4. **Active voice.** "This keeps quorum", not "quorum is preserved".
5. **Short sentences** (~20 words max in a step).
6. **One term per concept.** Pick one word for a thing and reuse it verbatim; don't
   elegant-variation between "config", "configuration", "settings".
7. **Warnings/cautions come first, then the consequence.** State the condition, then
   what it causes, then what to do. Put them in a callout, not buried in prose.
8. Keep code/config blocks verbatim. Do not "improve" commands or values.

Do NOT import from STE: its approved-word dictionary, its ban on idiom, its
sentence-length cap on prose. Those are for maintenance manuals and will wreck the
analytical sections. Procedural rules stop at the edge of the procedure.

### Analytical rules (from Gopen & Swan + Williams)

Goal: make reasoning flow and land, while keeping voice fully intact. These govern
*structure*, not vocabulary — they never tell you to simplify or de-idiom.

1. **Stress position — end sentences on what matters.** The reader remembers the last
   thing in a sentence. Put the payoff, the result, the name you're introducing, at
   the end; put context/setup at the start.
   - Weak: "Bound the events count via TTL and you bound the LIST cost, which is the fix."
   - Strong: "Bound the events count with a TTL, and you bound the cost of every LIST.
     That is the fix."
2. **Old-before-new cohesion.** Open each sentence/paragraph with information the
   previous one just established; end on the new idea. This is what turns a list of
   facts into a chain of reasoning. If two adjacent sentences don't share a hand-off
   term, the thread is broken — reorder until they do.
3. **Convert reasoning bullets to linked prose.** Bullets fragment an argument into
   disconnected assertions. If a bulleted list is really *symptom → cause → evidence*,
   rewrite it as flowing paragraphs with old-new hand-offs. Keep bullets only for
   genuinely parallel items (a list of configs, a set of independent gotchas).
4. **Character-as-subject, action-as-verb.** Put a concrete agent in the subject slot
   and its action in the verb. Kills vague "it was…" openings and nominalisations.
   - Weak: "It was CPU / range-scan bound." / "Orphaning of the config occurred."
   - Strong: "The VMs were range-scan bound." / "The migration orphaned the config."
5. **Structure a diagnosis as claim → evidence → warrant** (Craft of Research /
   Toulmin). State the conclusion, give the measurements that support it, name the
   mechanism that connects them. A debugging section should read in that order.
6. **Cut throat-clearing, keep voice.** Remove hedging filler ("it's worth noting
   that", "in order to", "the tradeoff to call out, because it's a real one"). Do NOT
   remove genuine voice — self-deprecation, dry asides, vivid metaphor. The test:
   filler carries no information; voice carries tone and is often the memorable line.

### Off-limits in BOTH modes — preserve, do not touch

- First-person reasoning and admissions ("I nearly drew the wrong conclusion").
- Dry humour and vivid images ("a 7-hour offset will happily sell you a fake story").
- Idiom and metaphor in analytical prose (sawtooth, head-of-line blocking, "falls
  over"). Only de-idiom inside procedures.
- The piece's disclaimer/meta line at the top ("This is a note — quick thoughts…").
- Numbers, measurements, code, and config values. Never round or paraphrase these.
- Bilingual/casual register where it appears. (Never insert Malaysian particles like
  "lah"; also never strip the author's existing register to sound corporate.)

### Micro-examples for calibration

Procedural, before → after:
> "Applying `--event-ttl` means re-rendering the apiserver config and doing a rolling
> control-plane restart, one node at a time so quorum is preserved."
→
> To apply `--event-ttl`:
> 1. Render the apiserver configuration again.
> 2. Restart the control-plane nodes one at a time. This keeps quorum.

Analytical, before → after (stress + character-as-subject + old-new):
> "It was not disk (WAL fsync ~3ms) and not memory. It was CPU / range-scan bound."
→
> "The cause was not where I first looked. Disk was healthy (WAL fsync ~3ms), and so
> was memory. What was saturated was CPU — the small control-plane VMs were
> range-scan bound."

### Order of operations when reworking a piece

1. Split the piece into blocks; classify each as procedural or analytical.
2. Apply the matching ruleset per block.
3. Re-read across block boundaries; fix old-new hand-offs between adjacent paragraphs.
4. Verify the off-limits list survived untouched (voice, numbers, code, disclaimer).
5. Leave a short changelog of structural moves made (not a full diff).

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
├── package.json              # Deps: marked, gray-matter, highlight.js
├── Makefile                  # Build/preview/new-article commands
├── content/
│   ├── articles/             # Human-written articles (YAML frontmatter + body)
│   ├── notes/                # Agent-written quick notes — concise, point-based
│   └── experiments/          # Agent-written research logs — scientific style
├── static/
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

## Frontend Stack

- **Tailwind CSS** via CDN — no build step, configured inline
- **Alpine.js** via CDN — dark mode toggle with localStorage persistence
- **highlight.js** via CDN — code syntax highlighting (github/github-dark themes)
- **@tailwindcss/typography** — prose classes for article content (via Tailwind CDN plugin config)

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
