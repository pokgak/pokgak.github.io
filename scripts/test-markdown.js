#!/usr/bin/env node
// Guards the raw-HTML-block handling in build.js. This failure mode is silent:
// markdown ends a raw HTML block at the first blank line and turns the indented
// remainder into a syntax-highlighted code block, so a broken inline SVG still
// builds and still deploys - it just renders as escaped source.

const { renderMarkdown } = require('../build.js');

let failures = 0;

function check(name, fn) {
  try {
    fn();
    console.log(`PASS: ${name}`);
  } catch (err) {
    failures++;
    console.error(`FAIL: ${name}\n      ${err.message}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const SVG_WITH_BLANK_LINES = `Intro paragraph.

<figure>
<svg viewBox="0 0 10 10">
  <g fill="currentColor">
    <rect x="1" y="1" width="4" height="4"/>

    <rect x="5" y="5" width="4" height="4"/>
  </g>
</svg>
<figcaption>A caption</figcaption>
</figure>

Closing paragraph.
`;

check('inline SVG survives blank lines inside the block', () => {
  const html = renderMarkdown(SVG_WITH_BLANK_LINES);
  assert(!html.includes('&lt;rect'), 'SVG markup was escaped into text');
  assert(!/<pre|<code/.test(html), 'SVG tail became a code block');
  assert((html.match(/<rect/g) || []).length === 2, 'both <rect> elements should survive');
  assert(html.includes('</svg>'), 'closing </svg> missing');
});

check('surrounding markdown still renders', () => {
  const html = renderMarkdown(SVG_WITH_BLANK_LINES);
  assert(html.includes('<p>Intro paragraph.</p>'), 'prose before the block was lost');
  assert(html.includes('<p>Closing paragraph.</p>'), 'prose after the block was lost');
});

check('nested same-name tags are balanced, not cut at the first close', () => {
  const html = renderMarkdown('<div class="a">\n<div class="b">\n\nx\n</div>\n</div>\n');
  assert((html.match(/<div/g) || []).length === 2, 'expected both divs preserved');
  assert((html.match(/<\/div>/g) || []).length === 2, 'expected both closers preserved');
});

check('an unterminated block is left to markdown rather than swallowing the file', () => {
  const html = renderMarkdown('<div>\n\nstill here\n');
  assert(html.includes('still here'), 'content after an unbalanced tag was swallowed');
});

check('fenced code blocks are still highlighted', () => {
  const html = renderMarkdown('```js\nconst a = 1;\n```\n');
  assert(html.includes('hljs'), 'code highlighting regressed');
  assert(html.includes('&#39;') || html.includes('const'), 'code content missing');
});

check('markdown that merely mentions a tag is untouched', () => {
  const html = renderMarkdown('Use the `<svg>` element.\n');
  assert(html.includes('<code'), 'inline code should stay inline code');
  assert(html.includes('&lt;svg&gt;'), 'inline code should stay escaped');
});

if (failures) {
  console.error(`\n${failures} markdown test(s) failed.`);
  process.exit(1);
}
console.log('\nMarkdown tests passed.');
