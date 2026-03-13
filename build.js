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
  return `<pre><code class="hljs language-${lang}">${highlighted}</code></pre>`;
};
marked.use({ renderer });

const SITE_TITLE = 'Aiman Ismail';
const SITE_URL = 'https://pokgak.xyz';
const CONTENT_DIR = path.join(__dirname, 'content/articles');
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

// --- Load articles ---

function loadArticles() {
  const files = fs.readdirSync(CONTENT_DIR).filter(f => f.endsWith('.md'));
  const articles = files.map(file => {
    const raw = fs.readFileSync(path.join(CONTENT_DIR, file), 'utf-8');
    const { data, content } = matter(raw);
    const slug = slugFromFilename(file);
    // Fix image paths: images/foo.png -> /images/foo.png
    const fixedContent = content.replace(/\]\(images\//g, '](/images/');
    const html = marked(fixedContent);
    return {
      title: data.title || slug,
      date: data.date ? new Date(data.date) : new Date(0),
      tags: data.tags || [],
      slug,
      html,
      content: fixedContent,
    };
  });
  articles.sort((a, b) => b.date - a.date);
  return articles;
}

// --- Templates ---

function baseLayout(title, content, { isHome = false } = {}) {
  const pageTitle = title;
  return `<!DOCTYPE html>
<html lang="en" x-data="{ dark: localStorage.getItem('dark') === 'true' }" x-init="$watch('dark', v => { localStorage.setItem('dark', v); document.getElementById('hljs-light').disabled = v; document.getElementById('hljs-dark').disabled = !v; }); document.getElementById('hljs-light').disabled = dark; document.getElementById('hljs-dark').disabled = !dark;" :class="{ 'dark': dark }">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeXml(pageTitle)}</title>
  <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: { extend: {} },
    }
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css" id="hljs-light">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" id="hljs-dark" disabled>
  <link rel="alternate" type="application/rss+xml" title="${escapeXml(SITE_TITLE)}" href="/index.xml">
  <!-- Analytics placeholder -->
  <style>
    .prose pre { @apply rounded-lg overflow-x-auto; max-width: 100%; }
    .prose pre code { font-size: 0.875em; white-space: pre; word-wrap: normal; overflow-wrap: normal; }
    .prose pre { padding: 0 !important; background-color: transparent !important; }
    .prose pre code.hljs { color: #24292e; background: #f6f8fa; display: block; padding: 1em; border-radius: 0.5rem; }
    .dark .prose pre code.hljs { color: #c9d1d9; background: #0d1117; }
    .prose img { @apply rounded-lg mx-auto; }
    .prose a { @apply underline decoration-gray-400 dark:decoration-gray-500 underline-offset-2 hover:decoration-gray-800 dark:hover:decoration-gray-200 transition-colors; }
  </style>
</head>
<body class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-200 min-h-screen flex flex-col">
  <header class="max-w-2xl mx-auto w-full px-6 py-8 flex items-center justify-between">
    <a href="/" class="text-lg font-semibold hover:opacity-75 transition-opacity">${escapeXml(SITE_TITLE)}</a>
    <nav class="flex items-center gap-6">
      <a href="/articles/" class="hover:opacity-75 transition-opacity">Articles</a>
      <button @click="dark = !dark" class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors" aria-label="Toggle dark mode">
        <svg x-show="!dark" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
        <svg x-show="dark" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
      </button>
    </nav>
  </header>

  <main class="max-w-2xl mx-auto w-full px-6 flex-1">
    ${content}
  </main>

  <footer class="max-w-2xl mx-auto w-full px-6 py-8 text-sm text-gray-500 dark:text-gray-400">
    <a href="/index.xml" class="hover:text-gray-700 dark:hover:text-gray-200 transition-colors">RSS</a>
  </footer>
</body>
</html>`;
}

function articleListItem(article) {
  return `<li class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4">
      <time class="text-sm text-gray-500 dark:text-gray-400 shrink-0" datetime="${article.date.toISOString()}">${formatDateShort(article.date)}</time>
      <a href="/articles/${article.slug}/" class="hover:opacity-75 transition-opacity">${escapeXml(article.title)}</a>
    </li>`;
}

function homePage(articles) {
  const latest = articles.slice(0, 5);
  return baseLayout(SITE_TITLE, `
    <section class="mb-12">
      <div class="flex gap-4 mb-8">
        <a href="https://github.com/pokgak" class="text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors" aria-label="GitHub">
          <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
        </a>
        <a href="https://www.linkedin.com/in/aiman-ismail-704158214/" class="text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors" aria-label="LinkedIn">
          <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
        </a>
        <a href="https://twitter.com/pokgak73" class="text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 transition-colors" aria-label="Twitter">
          <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24"><path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/></svg>
        </a>
      </div>
    </section>

    <section>
      <h2 class="text-xl font-semibold mb-6">Latest Articles</h2>
      <ul class="space-y-3 mb-6">
        ${latest.map(articleListItem).join('\n        ')}
      </ul>
      <a href="/articles/" class="text-sm hover:opacity-75 transition-opacity">View all &rarr;</a>
    </section>
  `, { isHome: true });
}

function articlesListPage(articles) {
  return baseLayout('Articles', `
    <h1 class="text-2xl font-semibold mb-8">Articles</h1>
    <ul class="space-y-3">
      ${articles.map(articleListItem).join('\n      ')}
    </ul>
  `);
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
  `);
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
  const articles = loadArticles();
  console.log(`Found ${articles.length} articles`);

  // Clean and create public dir
  fs.rmSync(PUBLIC_DIR, { recursive: true, force: true });
  ensureDir(PUBLIC_DIR);

  // Home page
  fs.writeFileSync(path.join(PUBLIC_DIR, 'index.html'), homePage(articles));

  // Articles list
  ensureDir(path.join(PUBLIC_DIR, 'articles'));
  fs.writeFileSync(path.join(PUBLIC_DIR, 'articles/index.html'), articlesListPage(articles));

  // Individual articles
  for (const article of articles) {
    const dir = path.join(PUBLIC_DIR, 'articles', article.slug);
    ensureDir(dir);
    fs.writeFileSync(path.join(dir, 'index.html'), articlePage(article));
  }

  // RSS feed
  fs.writeFileSync(path.join(PUBLIC_DIR, 'index.xml'), rssFeed(articles));

  // Copy static assets
  copyDirSync(path.join(STATIC_DIR, 'images'), path.join(PUBLIC_DIR, 'images'));

  console.log('Build complete! Output in public/');
}

build();
