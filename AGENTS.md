# ManimGX animations

Use ManimGX for explanatory motion that clarifies a sequence, state change, or
data flow. Do not add animation only for decoration, and do not replace an
existing interactive visualization when its controls are part of the lesson.

## Authoring and assets

- Use Python 3.13 or newer and pin `manimgx==0.1.1` in the animation's
  reproducible environment.
- Keep scene source and supporting files in `animations/<content-slug>/`.
- Commit the rendered H.264 file to `static/videos/<content-slug>.mp4`. GitHub
  Pages builds remain Node-only and must not render ManimGX scenes in CI.
- Never render into `public/`; the build deletes and regenerates that directory.
- Render at 1280×720 and 30 fps unless the visual demonstrably needs more.
  Target 1–2 MB per animation and review any file larger than 5 MB.
- Keep blog animations silent and self-explanatory. Motion must remain opt-in;
  never autoplay.
- ManimGX skips SVG `<text>` when importing with `SVGMobject`. Convert important
  labels to paths or recreate them with ManimGX text objects.

Typical validation and render commands:

```bash
manimgx inspect animations/<content-slug>/scene.py
manimgx render animations/<content-slug>/scene.py \
  -r 1280x720 --fps 30 -o static/videos/<content-slug>.mp4
```

## Typography

The blog uses Tailwind's `ui-sans-serif, system-ui, sans-serif` stack. Use the
bundled Noto Sans face as its deterministic ManimGX equivalent:

```python
body = m.Text("Body", font="sans-serif", weight=m.NORMAL)
label = m.Text("Label", font="sans-serif", weight=m.MEDIUM)
heading = m.Text("Heading", font="sans-serif", weight=m.SEMIBOLD)
code = m.Text("10.0.0.1", font="monospace", weight=m.NORMAL)
```

- Set `font="sans-serif"` on every prose or UI `Text` object. Omitting `font`
  selects New Computer Modern serif, which does not match the blog.
- Use normal (400) for body text, medium (500) for labels, and semibold (600)
  for headings. Reserve bold for a deliberate high-emphasis moment.
- Use `font="monospace"` only for code, commands, addresses, and identifiers.
- Do not request host fonts such as `system-ui`, Arial, or Inter. They are not
  deterministic across render environments; ManimGX's generic sans and mono
  families resolve to its bundled Noto Sans and DejaVu Sans Mono fonts.

## Embedding

For a simple silent animation whose adjacent prose is already a complete text
alternative, use Markdown image syntax. The build converts an MP4 reference
into a native video player:

```markdown
![Describe the process shown in the animation](videos/<content-slug>.mp4)
```

The description becomes the player's accessible name. Describe the process,
not the media (avoid labels such as "animation" or "video").

For a complex animation, use preserved raw HTML to associate the player with an
equivalent text description. Add a poster or caption track when applicable:

- Generate the poster from a representative frame of the finished animation,
  after typography and layout are final. Do not reuse a legacy hand-drawn
  diagram by default.
- Choose an informative state rather than a blank or title-only opening frame.
- Store it as `static/images/<content-slug>-poster.png` and target less than
  200 KB where practical.
- Replace the old diagram embed instead of showing both. Delete the old image
  only after `rg` confirms that no content or metadata still references it.

```html
<figure>
<video class="blog-video" controls playsinline preload="metadata"
  poster="/images/<content-slug>-poster.png"
  aria-label="A request moving through the Kubernetes network"
  aria-describedby="<content-slug>-description">
  <source src="/videos/<content-slug>.mp4" type="video/mp4">
  <track kind="captions" src="/videos/<content-slug>.vtt"
    srclang="en" label="English">
  <a href="/videos/<content-slug>.mp4">Download the animation</a>.
</video>
<figcaption id="<content-slug>-description">
  The request first resolves the Service name to a ClusterIP. Iptables then
  rewrites that destination to a Pod IP before the packet leaves the node.
</figcaption>
</figure>
```

Prefer pre-rendered MP4 over the live `<manimgx-player>` browser component. The
live player downloads roughly 26 MB of Pyodide and ManimGX, requires WebGPU,
and has a substantially larger compatibility and accessibility surface.

## Accessibility

Treat the text alternative as part of the animation, not as follow-up work.
Screen readers cannot interpret labels, arrows, or state changes rendered into
video frames.

- Give every player a concise accessible name that states its subject.
- Provide an equivalent text description in the article's reading order. For
  complex visuals, identify it with `aria-describedby` as shown above. Describe
  the ordered states, transitions, and conclusion, including information shown
  only through position, color, or motion.
- Keep the article understandable when the video is not played or cannot be
  seen. A poster is a visual fallback, not a screen-reader alternative.
- Caption all spoken audio and meaningful sounds. If essential information is
  visual-only, provide an equivalent transcript or audio description; do not
  rely on a caption track alone.
- Use native controls and preserve keyboard operation. Do not add custom
  overlays unless they meet the same keyboard and screen-reader behavior.
- Never autoplay. Avoid flashing more than three times per second, honor
  reduced-motion preferences, meet text/background contrast requirements, and
  never use color as the only way to distinguish a state.

## Verification

1. Run `manimgx inspect` before the final render.
2. Run `npm test` and `npm run build`.
3. Preview the affected page and verify play, pause, scrubbing, and fullscreen.
4. Inspect the accessibility tree. Confirm that the player has a useful name,
   its `aria-describedby` target exists when used, and the full visual sequence
   has an equivalent text description.
5. Operate playback with the keyboard and confirm controls have meaningful
   screen-reader names.
6. Inspect desktop and narrow mobile layouts in light and dark modes. Confirm
   that controls remain visible and the player causes no horizontal overflow.
7. Check the committed MP4 size and confirm the article still communicates the
   same facts when the animation is not played or cannot be seen.
