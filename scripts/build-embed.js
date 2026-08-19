#!/usr/bin/env node
// Wraps the interactive Maglev/Rendezvous page (authored as a fragment) into a
// standalone document under static/embeds/, adding two host-page modes:
//   ?embed=1     hide the masthead - the article supplies the title
//   ?only=<id>   show a single section's panel, for inline figure-sized iframes
const fs = require('fs');
const path = require('path');

const SRC = process.argv[2];
const DST = path.join(__dirname, '..', 'static/embeds/maglev-vs-rendezvous/index.html');

let s = fs.readFileSync(SRC, 'utf8');
const guard = /<script>if\(!document\.querySelector\('meta\[name="viewport"\]'\)\)[\s\S]*?<\/script>\n/;
s = s.replace(guard, '');

const headEnd = s.indexOf('</style>') + '</style>'.length;
const head = s.slice(0, headEnd);
const body = s.slice(headEnd).trim();

const HOST_CSS = `
<style>
  /* Embedded in a post: the host page supplies the title and the spacing. */
  html.embedded .masthead { display: none; }
  html.embedded .page { padding-top: var(--step-4); padding-bottom: var(--step-5); }
  html.embedded section:first-of-type { padding-top: 0; }

  /* Single-section mode: just the interactive panel, sized as a figure. */
  html[data-only="build"] .masthead, html[data-only="build"] .colophon,
  html[data-only="build"] section:not(#build),
  html[data-only="lab"] .masthead, html[data-only="lab"] .colophon,
  html[data-only="lab"] section:not(#lab) { display: none; }
  html[data-only] .sec-head, html[data-only] section > .prose { display: none; }
  html[data-only] section { padding-top: 0; }
  html[data-only] .page { max-width: 100%; padding: var(--step-3) var(--step-3) var(--step-3); }
  html[data-only] .panel { margin-top: 0; }
  html[data-only] body { background: var(--surface); }
</style>
`;

const HOST_JS = `
<script>
  (function () {
    var q = new URLSearchParams(location.search);
    var r = document.documentElement;
    if (q.has('embed') || window.self !== window.top) r.classList.add('embedded');
    var only = q.get('only');
    if (only === 'build' || only === 'lab') r.setAttribute('data-only', only);
  })();
</script>
`;

const out = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Interactive comparison of the Maglev and Rendezvous backend-selection algorithms, with a live churn simulation over 20,000 flows.">
${head}${HOST_CSS}${HOST_JS}</head>
<body>
${body}
</body>
</html>
`;

if (!/^[\x00-\x7F]*$/.test(out)) throw new Error('non-ASCII in embed output');
fs.mkdirSync(path.dirname(DST), { recursive: true });
fs.writeFileSync(DST, out);
console.log(`Wrote ${path.relative(path.join(__dirname, '..'), DST)} (${out.length} bytes)`);
