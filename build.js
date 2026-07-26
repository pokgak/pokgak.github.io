const fs = require('fs');
const path = require('path');
const matter = require('gray-matter');
const { marked } = require('marked');
const hljs = require('highlight.js');

// Configure marked with highlight.js using renderer
const renderer = new marked.Renderer();
renderer.code = function (code, lang) {
  lang = (lang || '').split(/\s/)[0];
  let highlighted;
  if (lang && hljs.getLanguage(lang)) {
    highlighted = hljs.highlight(code, { language: lang }).value;
  } else {
    highlighted = hljs.highlightAuto(code).value;
  }
  return `<pre tabindex="0"><code class="hljs language-${lang}">${highlighted}</code></pre>`;
};
marked.use({ renderer });

const SITE_TITLE = 'Aiman Ismail';
const SITE_URL = 'https://pokgak.xyz';
const SITE_DESCRIPTION = 'Writing by Aiman Ismail about infrastructure, observability, databases, Kubernetes, and AI engineering.';
const ARTICLES_DIR = path.join(__dirname, 'content/articles');
const NOTES_DIR = path.join(__dirname, 'content/notes');
const EXPERIMENTS_DIR = path.join(__dirname, 'content/experiments');
const TALKS_DIR = path.join(__dirname, 'content/talks');
const PUBLIC_DIR = path.join(__dirname, 'public');
const STATIC_DIR = path.join(__dirname, 'static');

// --- Helpers ---

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function copyDirSync(src, dest) {
  if (!fs.existsSync(src)) return;
  ensureDir(dest);
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirSync(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function slugFromFilename(filename) {
  return filename.replace(/\.md$/, '');
}

function formatDate(date) {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
}

function formatDateShort(date) {
  return new Date(date).toISOString().slice(0, 10);
}

function escapeXml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function normalizeLang(lang) {
  const value = typeof lang === 'string' ? lang.trim() : 'en';
  return /^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(value) ? value : 'en';
}

function navLink(href, label, section, currentSection) {
  const current = section === currentSection ? ' aria-current="page"' : '';
  return `<a href="${href}" class="hover:opacity-75 transition-opacity"${current}>${label}</a>`;
}

// --- Load content ---

function loadTalks(dir) {
  if (!fs.existsSync(dir)) return [];
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.md') && f !== 'CLAUDE.md');
  const items = files.map(file => {
    const raw = fs.readFileSync(path.join(dir, file), 'utf-8');
    const { data, content } = matter(raw);
    const slug = slugFromFilename(file);
    const html = marked(content);
    return {
      title: data.title || slug,
      date: data.date ? new Date(data.date) : new Date(0),
      tags: data.tags || [],
      event: data.event || '',
      embed_url: data.embed_url || '',
      slides_pdf: data.slides_pdf || '',
      thumbnail: data.thumbnail || '',
      lang: normalizeLang(data.lang),
      slug,
      html,
    };
  });
  items.sort((a, b) => b.date - a.date);
  return items;
}

function loadContent(dir) {
  if (!fs.existsSync(dir)) return [];
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.md') && f !== 'CLAUDE.md');
  const items = files.map(file => {
    const raw = fs.readFileSync(path.join(dir, file), 'utf-8');
    const { data, content } = matter(raw);
    const slug = slugFromFilename(file);
    const fixedContent = content.replace(/\]\(images\//g, '](/images/');
    const html = marked(fixedContent);
    return {
      title: data.title || slug,
      date: data.date ? new Date(data.date) : new Date(0),
      tags: data.tags || [],
      lang: normalizeLang(data.lang),
      slug,
      html,
      content: fixedContent,
    };
  });
  items.sort((a, b) => b.date - a.date);
  return items;
}

// --- Templates ---

function baseLayout(title, content, { lang = 'en', currentSection = '', description = SITE_DESCRIPTION } = {}) {
  const pageTitle = title;
  return `<!DOCTYPE html>
<html lang="${escapeXml(normalizeLang(lang))}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="${escapeXml(description)}">
  <title>${escapeXml(pageTitle)}</title>
  <script>try{if(localStorage.getItem('dark')==='true')document.documentElement.classList.add('dark')}catch(e){}</script>
  <link rel="stylesheet" href="/styles.css">
  <link rel="icon" href="/images/sprite.svg" type="image/svg+xml">
  <link rel="alternate" type="application/rss+xml" title="${escapeXml(SITE_TITLE)}" href="/index.xml">
  <!-- Analytics placeholder -->
</head>
<body class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-200 min-h-screen flex flex-col text-base lg:text-lg">
  <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:text-gray-900 focus:shadow-lg dark:focus:bg-gray-800 dark:focus:text-white">Skip to content</a>
  <header class="max-w-2xl mx-auto w-full px-6 py-6 sm:py-8 flex flex-wrap items-center justify-between gap-y-2">
    <a href="/" class="text-lg font-semibold hover:opacity-75 transition-opacity">${escapeXml(SITE_TITLE)}</a>
    <nav class="flex items-center gap-4 sm:gap-6 text-sm sm:text-base" aria-label="Primary">
      ${navLink('/articles/', 'Articles', 'articles', currentSection)}
      ${navLink('/notes/', 'Notes', 'notes', currentSection)}
      ${navLink('/experiments/', 'Experiments', 'experiments', currentSection)}
      ${navLink('/talks/', 'Talks', 'talks', currentSection)}
      <button id="theme-toggle" type="button" class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors" aria-pressed="false" aria-label="Enable dark mode">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 dark:hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true" focusable="false"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
        <svg xmlns="http://www.w3.org/2000/svg" class="hidden h-5 w-5 dark:block" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true" focusable="false"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
      </button>
    </nav>
  </header>

  <main id="main-content" tabindex="-1" class="max-w-2xl mx-auto w-full px-6 flex-1">
    ${content}
  </main>

  <footer class="max-w-2xl mx-auto w-full px-6 py-8 text-sm text-gray-500 dark:text-gray-400">
    <a href="/index.xml" class="hover:text-gray-700 dark:hover:text-gray-200 transition-colors">RSS</a>
  </footer>
  <script>
    (() => {
      const root = document.documentElement;
      const toggle = document.getElementById('theme-toggle');
      const updateToggle = () => {
        const dark = root.classList.contains('dark');
        toggle.setAttribute('aria-pressed', String(dark));
        toggle.setAttribute('aria-label', dark ? 'Disable dark mode' : 'Enable dark mode');
      };
      updateToggle();
      toggle.addEventListener('click', () => {
        root.classList.toggle('dark');
        try { localStorage.setItem('dark', String(root.classList.contains('dark'))); } catch (e) {}
        updateToggle();
      });
    })();
  </script>
</body>
</html>`;
}

function articleListItem(article) {
  return `<li class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
      <time class="text-sm text-gray-500 dark:text-gray-400 shrink-0" datetime="${article.date.toISOString()}">${formatDateShort(article.date)}</time>
      <a href="/articles/${article.slug}/" class="hover:opacity-75 transition-opacity">${escapeXml(article.title)}</a>
    </li>`;
}

// Type badge shown in the merged homepage feed: a lowercase outline pill, kept
// quieter than the filled tag badges on the article/note/experiment pages so it
// reads as a marker rather than a label. Ink is tinted per type.
const FEED_TYPES = {
  article: { label: 'article', dir: 'articles', ink: 'text-[#4b5563] dark:text-[#cbd5e1]' },
  note: { label: 'note', dir: 'notes', ink: 'text-[#7c6f52] dark:text-[#cbb994]' },
  experiment: { label: 'experiment', dir: 'experiments', ink: 'text-[#4d6b7c] dark:text-[#93c0d6]' },
};

// Date and badge sit side by side on narrow screens with the title beneath, and
// stack into a fixed left column from sm up so the titles align.
function feedListItem(item) {
  const kind = FEED_TYPES[item.type];
  return `<li class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
      <span class="flex items-center gap-2 sm:w-28 sm:shrink-0 sm:flex-col sm:items-start sm:gap-1">
        <time class="text-sm leading-none text-gray-500 dark:text-gray-400 tabular-nums" datetime="${item.date.toISOString()}">${formatDateShort(item.date)}</time>
        <span class="text-[0.7rem] leading-none px-1.5 py-1 rounded-full border border-gray-200 dark:border-gray-700 ${kind.ink}">${kind.label}</span>
      </span>
      <a href="/${kind.dir}/${item.slug}/" class="leading-snug hover:opacity-75 transition-opacity">${escapeXml(item.title)}</a>
    </li>`;
}

function homePage(articles, notes, experiments) {
  const feed = [
    ...articles.map(a => ({ ...a, type: 'article' })),
    ...notes.map(n => ({ ...n, type: 'note' })),
    ...experiments.map(e => ({ ...e, type: 'experiment' })),
  ]
    .sort((a, b) => b.date - a.date)
    .slice(0, 10);

  return baseLayout(SITE_TITLE, `
    <section>
      <h1 class="text-xl font-semibold mb-6">Latest Writing</h1>
      <ul class="space-y-5 sm:space-y-3">
        ${feed.map(feedListItem).join('\n        ')}
      </ul>
    </section>

    <section class="mt-16 flex flex-col items-center gap-5">
      <img src="/images/sprite.svg" alt="Pixel art portrait of Aiman Ismail" class="w-20 h-20" style="image-rendering: pixelated;" />
      <div class="flex gap-4">
        <a href="https://github.com/pokgak" class="text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors" aria-label="GitHub">
          <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
        </a>
        <a href="https://www.linkedin.com/in/aiman-ismail-704158214/" class="text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors" aria-label="LinkedIn">
          <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
        </a>
        <a href="https://twitter.com/pokgak73" class="text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors" aria-label="Twitter">
          <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/></svg>
        </a>
      </div>
    </section>
  `);
}

function articlesListPage(articles) {
  return baseLayout('Articles', `
    <h1 class="text-2xl font-semibold mb-8">Articles</h1>
    <ul class="space-y-3">
      ${articles.map(articleListItem).join('\n      ')}
    </ul>
  `, { currentSection: 'articles' });
}

function articlePage(article) {
  const tags = article.tags.length
    ? `<div class="flex flex-wrap gap-2 mb-8">${article.tags.map(t => `<span class="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">${escapeXml(t)}</span>`).join('')}</div>`
    : '';

  return baseLayout(article.title, `
    <article>
      <header class="mb-8">
        <h1 class="text-2xl font-semibold mb-2">${escapeXml(article.title)}</h1>
        <time class="text-sm text-gray-500 dark:text-gray-400" datetime="${article.date.toISOString()}">${formatDate(article.date)}</time>
      </header>
      ${tags}
      <div class="prose prose-gray dark:prose-invert max-w-none
        prose-headings:font-semibold
        prose-pre:bg-gray-50 prose-pre:dark:bg-gray-800
        prose-code:before:content-none prose-code:after:content-none
        prose-code:bg-gray-100 prose-code:dark:bg-gray-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
        prose-img:rounded-lg">
        ${article.html}
      </div>
    </article>
  `, { lang: article.lang, currentSection: 'articles' });
}

function noteListItem(note) {
  return `<li class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
      <time class="text-sm text-gray-500 dark:text-gray-400 shrink-0" datetime="${note.date.toISOString()}">${formatDateShort(note.date)}</time>
      <a href="/notes/${note.slug}/" class="hover:opacity-75 transition-opacity">${escapeXml(note.title)}</a>
    </li>`;
}

function notesListPage(notes) {
  return baseLayout('Notes', `
    <h1 class="text-2xl font-semibold mb-2">Notes</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mb-8">Quick thoughts and rough ideas — less polished than articles, possibly AI-assisted.</p>
    <ul class="space-y-3">
      ${notes.map(noteListItem).join('\n      ')}
    </ul>
  `, { currentSection: 'notes' });
}

function notePage(note) {
  const tags = note.tags.length
    ? `<div class="flex flex-wrap gap-2 mb-8">${note.tags.map(t => `<span class="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">${escapeXml(t)}</span>`).join('')}</div>`
    : '';

  return baseLayout(note.title, `
    <article>
      <header class="mb-8">
        <h1 class="text-2xl font-semibold mb-2">${escapeXml(note.title)}</h1>
        <time class="text-sm text-gray-500 dark:text-gray-400" datetime="${note.date.toISOString()}">${formatDate(note.date)}</time>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1 italic">This is a note — quick thoughts, possibly AI-assisted. Not a fully fleshed article.</p>
      </header>
      ${tags}
      <div class="prose prose-gray dark:prose-invert max-w-none
        prose-headings:font-semibold
        prose-pre:bg-gray-50 prose-pre:dark:bg-gray-800
        prose-code:before:content-none prose-code:after:content-none
        prose-code:bg-gray-100 prose-code:dark:bg-gray-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
        prose-img:rounded-lg">
        ${note.html}
      </div>
    </article>
  `, { lang: note.lang, currentSection: 'notes' });
}

function experimentListItem(experiment) {
  return `<li class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
      <time class="text-sm text-gray-500 dark:text-gray-400 shrink-0" datetime="${experiment.date.toISOString()}">${formatDateShort(experiment.date)}</time>
      <a href="/experiments/${experiment.slug}/" class="hover:opacity-75 transition-opacity">${escapeXml(experiment.title)}</a>
    </li>`;
}

function experimentsListPage(experiments) {
  return baseLayout('Experiments', `
    <h1 class="text-2xl font-semibold mb-2">Experiments</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mb-2">Structured investigations following a scientific approach: each experiment starts with a question, states a hypothesis, runs a method, presents results, then draws conclusions. Multiple experiments build toward a final answer.</p>
    <p class="text-sm text-gray-500 dark:text-gray-400 mb-8">Raw data and observations — not polished write-ups.</p>
    <ul class="space-y-3">
      ${experiments.map(experimentListItem).join('\n      ')}
    </ul>
  `, { currentSection: 'experiments' });
}

function experimentPage(experiment) {
  const tags = experiment.tags.length
    ? `<div class="flex flex-wrap gap-2 mb-8">${experiment.tags.map(t => `<span class="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">${escapeXml(t)}</span>`).join('')}</div>`
    : '';

  return baseLayout(experiment.title, `
    <article>
      <header class="mb-8">
        <h1 class="text-2xl font-semibold mb-2">${escapeXml(experiment.title)}</h1>
        <time class="text-sm text-gray-500 dark:text-gray-400" datetime="${experiment.date.toISOString()}">${formatDate(experiment.date)}</time>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1 italic">This is an experiment — raw data and observations, not a polished write-up.</p>
      </header>
      ${tags}
      <div class="prose prose-gray dark:prose-invert max-w-none
        prose-headings:font-semibold
        prose-pre:bg-gray-50 prose-pre:dark:bg-gray-800
        prose-code:before:content-none prose-code:after:content-none
        prose-code:bg-gray-100 prose-code:dark:bg-gray-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
        prose-img:rounded-lg">
        ${experiment.html}
      </div>
    </article>
  `, { lang: experiment.lang, currentSection: 'experiments' });
}

function talkListItem(talk) {
  const thumb = talk.thumbnail
    ? `<a href="/talks/${talk.slug}/" class="block mb-3 hover:opacity-75 transition-opacity">
        <img src="/images/${escapeXml(talk.thumbnail)}" alt="" class="w-full rounded-lg aspect-video object-cover">
      </a>`
    : '';
  return `<li class="flex flex-col gap-1">
      ${thumb}
      <div class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
        <time class="text-sm text-gray-500 dark:text-gray-400 shrink-0" datetime="${talk.date.toISOString()}">${formatDateShort(talk.date)}</time>
        <a href="/talks/${talk.slug}/" class="hover:opacity-75 transition-opacity">${escapeXml(talk.title)}</a>
      </div>
      ${talk.event ? `<p class="text-sm text-gray-500 dark:text-gray-400 sm:pl-[calc(10ch+1rem)]">${escapeXml(talk.event)}</p>` : ''}
    </li>`;
}

function talksListPage(talks) {
  return baseLayout('Talks', `
    <h1 class="text-2xl font-semibold mb-8">Talks</h1>
    <ul class="space-y-6">
      ${talks.map(talkListItem).join('\n      ')}
    </ul>
  `, { currentSection: 'talks' });
}

function talkPage(talk) {
  const embed = talk.embed_url
    ? `<div class="relative w-full mb-8" style="padding-top: 56.25%;">
        <iframe src="${escapeXml(talk.embed_url)}" title="${escapeXml(talk.title)} presentation slides" allowfullscreen
          class="absolute inset-0 w-full h-full rounded-lg"></iframe>
      </div>`
    : talk.thumbnail
      ? `<img src="/images/${escapeXml(talk.thumbnail)}" alt="${escapeXml(talk.title)}" class="w-full rounded-lg mb-8">`
      : '';

  const pdfLink = talk.slides_pdf
    ? `<a href="${escapeXml(talk.slides_pdf)}" class="inline-flex items-center gap-1 text-sm hover:opacity-75 transition-opacity" download>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true" focusable="false"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h4a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
        Download PDF
      </a>`
    : '';

  const body = talk.html
    ? `<div class="prose prose-gray dark:prose-invert max-w-none mt-8
        prose-headings:font-semibold
        prose-code:before:content-none prose-code:after:content-none
        prose-code:bg-gray-100 prose-code:dark:bg-gray-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded">
        ${talk.html}
      </div>`
    : '';

  return baseLayout(talk.title, `
    <article>
      <header class="mb-8">
        <h1 class="text-2xl font-semibold mb-2">${escapeXml(talk.title)}</h1>
        <div class="flex flex-wrap items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
          <time datetime="${talk.date.toISOString()}">${formatDate(talk.date)}</time>
          ${talk.event ? `<span>&middot;</span><span>${escapeXml(talk.event)}</span>` : ''}
        </div>
      </header>
      ${embed}
      ${pdfLink}
      ${body}
    </article>
  `, { lang: talk.lang, currentSection: 'talks' });
}

function rssFeed(articles) {
  const items = articles.slice(0, 20).map(a => `    <item>
      <title>${escapeXml(a.title)}</title>
      <link>${SITE_URL}/articles/${a.slug}/</link>
      <guid>${SITE_URL}/articles/${a.slug}/</guid>
      <pubDate>${a.date.toUTCString()}</pubDate>
      <description>${escapeXml(a.html)}</description>
    </item>`).join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${escapeXml(SITE_TITLE)}</title>
    <link>${SITE_URL}</link>
    <description>Articles by ${escapeXml(SITE_TITLE)}</description>
    <atom:link href="${SITE_URL}/index.xml" rel="self" type="application/rss+xml"/>
    ${items}
  </channel>
</rss>`;
}

// --- Build ---

function build() {
  console.log('Building site...');
  const articles = loadContent(ARTICLES_DIR);
  const notes = loadContent(NOTES_DIR);
  const experiments = loadContent(EXPERIMENTS_DIR);
  const talks = loadTalks(TALKS_DIR);
  console.log(`Found ${articles.length} articles, ${notes.length} notes, ${experiments.length} experiments, ${talks.length} talks`);

  // Clean and create public dir
  fs.rmSync(PUBLIC_DIR, { recursive: true, force: true });
  ensureDir(PUBLIC_DIR);

  // Home page
  fs.writeFileSync(path.join(PUBLIC_DIR, 'index.html'), homePage(articles, notes, experiments));

  // Articles list
  ensureDir(path.join(PUBLIC_DIR, 'articles'));
  fs.writeFileSync(path.join(PUBLIC_DIR, 'articles/index.html'), articlesListPage(articles));

  // Individual articles
  for (const article of articles) {
    const dir = path.join(PUBLIC_DIR, 'articles', article.slug);
    ensureDir(dir);
    fs.writeFileSync(path.join(dir, 'index.html'), articlePage(article));
  }

  // Notes list
  ensureDir(path.join(PUBLIC_DIR, 'notes'));
  fs.writeFileSync(path.join(PUBLIC_DIR, 'notes/index.html'), notesListPage(notes));

  // Individual notes
  for (const note of notes) {
    const dir = path.join(PUBLIC_DIR, 'notes', note.slug);
    ensureDir(dir);
    fs.writeFileSync(path.join(dir, 'index.html'), notePage(note));
  }

  // Experiments list
  ensureDir(path.join(PUBLIC_DIR, 'experiments'));
  fs.writeFileSync(path.join(PUBLIC_DIR, 'experiments/index.html'), experimentsListPage(experiments));

  // Individual experiments
  for (const experiment of experiments) {
    const dir = path.join(PUBLIC_DIR, 'experiments', experiment.slug);
    ensureDir(dir);
    fs.writeFileSync(path.join(dir, 'index.html'), experimentPage(experiment));
  }

  // Talks list
  ensureDir(path.join(PUBLIC_DIR, 'talks'));
  fs.writeFileSync(path.join(PUBLIC_DIR, 'talks/index.html'), talksListPage(talks));

  // Individual talks
  for (const talk of talks) {
    const dir = path.join(PUBLIC_DIR, 'talks', talk.slug);
    ensureDir(dir);
    fs.writeFileSync(path.join(dir, 'index.html'), talkPage(talk));
  }

  // RSS feed
  fs.writeFileSync(path.join(PUBLIC_DIR, 'index.xml'), rssFeed(articles));

  // Copy static assets
  copyDirSync(path.join(STATIC_DIR, 'images'), path.join(PUBLIC_DIR, 'images'));

  console.log('Build complete! Output in public/');
}

build();
